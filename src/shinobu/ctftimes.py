#-*- coding: utf-8 -*-
import sys
sys.path.append('../')
import feedparser
import ssl
import re
import json
import requests

from bs4 import BeautifulSoup

from read_json import json_obj
globals().update(json_obj[sys.argv[0]])

date_pat = re.compile(r'(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})')
link_pat = re.compile(r'<a href="(.+)" .+>(\[.+\])</a>')
prefix = "https://ctftime.org" #相対パスが多いので、プレフィックス

upcoming_url = "https://ctftime.org/event/list/upcoming/rss/"
icon_url = "https://pbs.twimg.com/profile_images/580883843109953536/S9L7XHd9.jpg"

#Official URLのハズなのになぜかOffical URLになってた。
filter_headers = ["Name", "Date", "Location", "Offical URL", "Rating weight", "Format", "Event organizers"]

#正しくないSSL証明書でも通信可能とする
if hasattr(ssl, '_create_unverified_context'):
	ssl._create_default_https_context = ssl._create_unverified_context

def post_to_slack(webhook_url, msg, icon_url):
	payload = {
		"channel": "#jvn_alert",
		"username": "忍野忍",
		"text": msg, #投稿するテキスト
		"icon_url": icon_url, #アイコン画像
	}
	jpayload = json.dumps(payload)
	res = requests.post(webhook_url, jpayload, headers={'Content-Type': 'application/json'})
	print("Response: {}".format(res))

def get_datetime(timestamp):
	year, month, day, hour, minute, second = re.findall(date_pat, timestamp)[0]
	return("{year}年{month}月{day}日 {hour}:{minute}:{second}".format(**locals()))

def add_prefix_url(url):
	if url.startswith('/'):
		return(prefix+url)
	return(url)

def optimize_links(s):
	soup = BeautifulSoup(s)

	for atag in soup.find_all("a"): #aタグをイテレート
		url = add_prefix_url(atag.get("href"))
		txt = atag.string
		atag.replace_with("<{url}|{txt}>".format(url=url, txt=txt))

	return soup.get_text()

def optimize_html(s):
	d = {}
	html = optimize_links(s)
	lines = html.split('\n')
	for idx, line in enumerate(lines):
		for fh in filter_headers:
			if line.startswith(fh):
				d[fh] = line.split(':', 1)[1]
				if fh.startswith("Event organizers"):
					d[fh] += ''.join(lines[idx+1:])
					d[fh] = d[fh].replace('\n', '\n>')


	return(html, d)

def make_msg(index, entry, separator='-'):
	ctf_id = entry['ctf_id']
	summary, explain_dict = optimize_html(entry['summary'])
	
	ctf = ""
	ctf += "({index})\n".format(index=index)
	ctf += ">タイトル: *{title}*\n".format(title=explain_dict['Name'])
	ctf += ">形式: *{format}*\n".format(format=explain_dict['Format'])
	ctf += ">日時: *{start} ~ {end}* {add2calendar}\n".format(start=get_datetime(entry['start_date']), end=get_datetime(entry['finish_date']), add2calendar=explain_dict['Date'].split('UTC')[1])
	if 'Location' in explain_dict:
		ctf += ">場所: *{location}*\n".format(location=explain_dict['Location'])
	ctf += ">公式URL: *{official_url}*\n".format(official_url=explain_dict['Offical URL'])
	ctf += ">レート: *{rate}*\n".format(rate=explain_dict['Rating weight'])
	if 'Event organizers' in explain_dict:
		ctf += ">イベント主催者たち: \n>*{organizers}*\n".format(organizers=explain_dict['Event organizers'])
	ctf += "\n"
	
	ctf += ">関連リンク:\n"
	for idx, link in enumerate(entry['links']):
		ctf += ">{idx}: {link}\n".format(idx=idx+1, link=link['href'])
	ctf += separator*180 + "\n\n\n"

	return ctf

def make_whole_msg(entries):
	whole_msg = ""
	for idx in range(len(entries)):
		whole_msg += make_msg(idx+1, entries[idx])

	return whole_msg

def fetch_entries():
	print("[+] Fetching feeds...")
	d = feedparser.parse(upcoming_url)
	print("[+] Parsed feeds.")
	entries = d['entries']
	return(entries)

if __name__ == '__main__':
	entries = fetch_entries()
	msg = make_whole_msg(entries)
	print(msg)
	print("Posting...")
	post_to_slack(webhook_url, msg, icon_url)

