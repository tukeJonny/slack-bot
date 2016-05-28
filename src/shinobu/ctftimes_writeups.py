#-*- coding: utf-8 -*-
import sys
sys.path.append('../')
import re
import ssl
from multiprocessing import Process, Queue
import queue
import feedparser
from bs4 import BeautifulSoup
import requests
from flask import Flask, jsonify, request

import ctftimes
from read_json import json_obj
globals().update(json_obj[sys.argv[0]])

app = Flask(__name__)
#writeups_url = "https://ctftime.org/writeups/rss/"

error_msg = "Fuck you! INVALID OPERATION!!!!!!! :rage:"

if hasattr(ssl, '_create_unverified_context'):
	ssl._create_default_https_context = ssl._create_unverified_context

class SlackMessage(object):
	token = ""
	team_id = ""
	channel_id = ""  #投稿されたチャンネルID
	channel_name = ""  #チャンネル名
	timestamp = 0
	user_id = ""  
	user_name = ""  #投稿ユーザー名
	text = ""  #投稿内容
	trigger_word = ""  #OutgoingWebhooksに設定したトリガー

	def __init__(self, params):
		self.token = params['token']
		self.team_id = params['team_id']
		self.channel_id = params["channel_id"]
		self.channel_name = params["channel_name"]
		self.timestamp = params["timestamp"]
		self.user_id = params["user_id"]
		self.user_name = params["user_name"]
		self.text = params["text"]
		self.trigger_word = params["trigger_word"]

	def __str__(self):
		res = self.__class__.__name__
		res += "@{0.token}[channel={0.channel_name}, user={0.user_name}, text={0.text}]".format(self)
		return res   

#忍ちゃん
#命令に従順に応じ、メッセージを作ってくれる
class Shinobu(object):

	def __init__(self, msg):
		self.__slack_msg = msg
		self.__limit_num = 30
		self.__keyword = ""
		self.__regex = False
		self.__full_entries = None
		self.__genre_queue = Queue()
		self.__url_queue = Queue()
		self.__entry_queue = Queue()
		
	############################# Setter and Getter #############################
	@property
	def limit_num(self):
		return self.__limit_num
	@limit_num.setter
	def limit_num(self, limit_num):
		if limit_num <= 20:
			self.__limit_num = limit_num

	@property
	def keyword(self):
	    return self.__keyword
	@keyword.setter
	def keyword(self, keyword):
		self.__keyword = keyword

	@property
	def regex(self):
	    return self.__regex
	@regex.setter
	def regex(self, regex):
		self.__regex = regex

	############################# Helper ############################# 

	#ヘルプテキスト表示
	def show_help(self):
		help_text = ""
		help_text += "_SYNOPSIS_:\n"
		help_text += ">	shinobu: [command]\n"
		help_text += "_COMMANDS_:\n"
		help_text += ">	help ... このヘルプテキストを表示\n"
		help_text += ">	writeups [num] ... CTFTime.orgからnum件のWriteupを取得(num <= 30)\n"
		help_text += ">	events ... CTFTime.orgから、イベント情報を取得（好きなタイミングで取得できるようになったよ♪)\n"
		help_text += ">	search-writeups [keyword] ... CTFTime.orgからkeywordにヒットしたWriteupを取得\n"
		help_text += ">	list-titles ... 全Writeupのタイトルを取得\n"
		help_text += ">	list-genres ... 全Writeupsのジャンルを取得(順不同)\n"
		help_text += ">	list-urls ... 全WriteupsのURLを取得(順不同)\n"
		return(return_json(help_text))

	#指定URLにアクセスし、ジャンルとWriteupのURLを取得してくる。CTFTimes.orgがJSONに含んでくれればこんな手間はいらない
	#genre_only ... list_genres()メソッドからの呼び出しの際に、Trueになる。
	#url_only   ... list_urls()メソッドからの呼び出しの際に、Trueになる。
	#ジャンルだけ取得したい場合、ジャンルをキューに突っ込む
	#URLだけ取得したい場合、URLをキューに突っ込む
	#どちらでもない場合、キューに突っ込まず、辞書にして返す
	def fetch_genre_and_url(self, url, url_only=False, genre_only=False):
		print("[+] Fetching genre {url} ...".format(url=url))
		try:
			response = requests.get(url)
		except Exception as err:
			print(err)
		soup = BeautifulSoup(response.text, "html.parser")
		
		url = None
		genre = None

		#ジャンルだけ取得したいという場合でなければ
		if not genre_only:
			url = soup.find("a", {"rel": "nofollow"}) #WriteupのURL候補１を取得
			orig_url = soup.find("a", {"target": "_new"}) #WriteupのURL候補２を取得

			#２つの候補から、正しい値が入っているものだけ取り出す
			if url is None:
				if orig_url is not None:
					url = orig_url.get("href")
				else:
					url = None
			else:
				url = url.get("href")
			#URLだけ取得したいのであれば
			if url_only:
				self.__url_queue.put(url) #URLをキューに突っ込む
				return
				
		
		genre = soup.find("span", {"class": "label label-info"}) 
		genre = "Unknown" if genre is None else genre.text 
		#ジャンルだけ取得したいのであれば
		if genre_only:
			self.__genre_queue.put(genre) #ジャンルをキューに突っ込む

		return({"genre": genre, "url": url})

	#entry(JSON)から、正しいURLを取り出す
	def getEffectiveURL(self, entry, url):
		if url is None:
			if len(entry['links']) > 0:
				url = entry['links'][0]['href']
			else:
				url = "Unknown"
		return url

	#検索時、キーワードに引っかかるかを返す
	def checkIncludeKeyword(self, writeup):
		if len(self.__keyword) > 0:
			return(self.__keyword.lower() in writeup.lower())
		return True

	############################# Make messages ############################# 

	#RSSフィードを取得し、
	#Writeupを取得する際、必ずこのメソッドが呼び出される
	def show_writeups(self, title_only=False, url_only=False, genre_only=False):
		d = feedparser.parse(writeups_url)
		entries = d['entries']
		#self.__full_entries = d['entries']
		msg=""
		if title_only:
			msg = self.list_titles(entries)
		elif url_only:
			msg = self.list_urls(entries)
		elif genre_only:
			msg = self.list_genres(entries)
		else:
			msg = self.make_whole_msg(entries)
		
		return(return_json(msg))

	#entriesを受け取り
	#entry一つ一つに対してmake_msgを呼び出すことで、えんとりごとのメッセージを取得
	#それらのメッセージを連結し、全体のメッセージとして返す。
	def make_whole_msg(self, entries):
		if self.__limit_num > len(entries):
			self.__limit_num = len(entries)
		if self.__limit_num == 0:
			return "No entries."

		whole_msg = ""	
		procs = [Process(target=self.make_msg, args=(idx+1, entries[idx])) for idx in range(self.__limit_num)]
		for proc in procs:
			proc.start()
		for proc in procs:
			proc.join()
		queue_entries = sorted([self.__entry_queue.get(timeout=3) for _ in range(self.__entry_queue.qsize())], key=lambda e: e[0])
		print("Queue: {}".format(queue_entries))
		for writeup in queue_entries:
			whole_msg += writeup[1]
		whole_msg += "Are there no writeups you want to read? Please access <https://ctftime.org/writeups|here>"
		return whole_msg

	#make_whole_msgから呼び出される
	#一つのえんとりを受け取り、そのえんとりのメッセージを返す。
	def make_msg(self, index, entry, separator='-'):
		result = self.fetch_genre_and_url(entry['links'][0]['href'])
		genre = result["genre"]
		url = result["url"]
		url = self.getEffectiveURL(entry, url)

		writeup = ""
		writeup += "({index})\n".format(index=index)
		writeup += ">_Title_: *{title}*\n".format(title=entry['title_detail']['value'])
		writeup += ">_Genre_: *{genre}*\n".format(genre=genre)
		writeup += ">_Writeup URL_: {url}\n".format(url=url)
		writeup += separator*180 + "\n\n\n"

		if self.checkIncludeKeyword(writeup):
			self.__entry_queue.put((index, writeup))
			

	############################# Listing ############################# 
	#Writeupのタイトル一覧を返す
	def list_titles(self, entries):
		msg = ""
		for entry in entries:
			msg += "{title}\n".format(title=entry['title_detail']['value'])
		msg += "Are there no writeups you want to read? Please access <https://ctftime.org/writeups|here>"
		return msg

	#Writeupのジャンル一覧を返す
	def list_genres(self, entries):
		msg = ""
		procs = [Process(target=self.fetch_genre_and_url, args=(entry['links'][0]['href'],False, True,)) for entry in entries]
		for proc in procs:
			proc.start()
		for proc in procs:
			proc.join()
		for _ in range(len(entries)):
			genre = self.__genre_queue.get(timeout=3)
			msg += "{genre}\n".format(genre=genre) if not "Unknown" in genre else ""
		
		return msg

	#WriteupのURL一覧を返す
	def list_urls(self, entries):
		msg = ""
		procs = [Process(target=self.fetch_genre_and_url, args=(entry['links'][0]['href'], True, False)) for entry in entries]
		for proc in procs:
			proc.start()
		for proc in procs:
			proc.join()
		for _ in range(len(entries)):
			url = self.__url_queue.get(timeout=3)
			msg += "{url}\n".format(url=url) if url is not None else ""
		return msg

slack_msg = None
#忍ちゃんを呼び出すメソッド(忍ちゃん本人ではないが、いわば利用者と忍ちゃんの間に存在するインタフェース)
#Slackの投稿にて、
#「shinobu: 」をトリガーに、命令文字列に対応したメソッドを呼び出す。
@app.route('/ctf-writeups', methods=['POST'])
def shinobu_chan():
	global slack_msg
	slack_msg = SlackMessage(request.form)
	shinobu = Shinobu(slack_msg)

		return error_msg
	
	if slack_msg.user_name == "slackbot":
		return ''
	
	if "search-writeups" in slack_msg.text:
		try:
			keyword = slack_msg.text.split(' ')[2]
		except Exception:
			return return_json(error_slack_msg)
		shinobu.keyword = keyword
		return shinobu.show_writeups()
	elif "writeups" in slack_msg.text:
		num = 0
		try:
			num = int(slack_msg.text.split(' ')[2])
		except Exception as ve:
			return return_json(error_msg)
		shinobu.limit_num = num
		return shinobu.show_writeups()
	elif "events" in slack_msg.text:
		entries = ctftimes.fetch_entries()
		return return_json(ctftimes.make_whole_msg(entries))
	elif "list-titles" in slack_msg.text:
		return shinobu.show_writeups(title_only=True)
	elif "list-genres" in slack_msg.text:
		return shinobu.show_writeups(genre_only=True)
	elif "list-urls" in slack_msg.text:
		return shinobu.show_writeups(url_only=True)
	elif "help" in slack_msg.text:
		return shinobu.show_help()
	elif "ping" in slack_msg.text:
		return return_json("64 bytes from 忍ちゃん: icmp_seq=1 ttl=50 time=68.277 ms :heart:")
	else:
		return return_json("ふえぇ...")

#メッセージを受け取り、それをJSON形式にして返す
def return_json(msg):
	print("Return contents below:\n {msg}".format(msg=msg))
	return(jsonify(
			{
				"text": msg
			}
		))

if __name__ == "__main__":
	app.run('0.0.0.0', 8000, debug=True)
