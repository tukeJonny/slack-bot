#-*- coding: utf-8 -*-
import sys
sys.path.append('../')
import random
import json
import re

import feedparser
import requests

from read_json import json_obj
globals().update(json_obj[sys.argv[0]])


url = "http://jvndb.jvn.jp/myjvn?method=getVulnOverviewList&maxCountItem=50&rangeDatePublic=w&rangeDateFirstPublished=w&rangeDatePublished=w&lang=ja"
icon_url = "http://matomame.jp/assets/images/matome/cdd56e93b32a719ceb74/d7da474287a0fa05c3e1424deafd0c65.jpg?t=1435669528"
date_pat = re.compile(r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})')

cve_dbs = [
	"CVE-Details: http://www.cvedetails.com/cve-details.php?t=1&cve_id={cve_id}", #CVE-Details
	"JVNDB: http://jvn.jp/jp/{cve_id}/index.html" #JVN "#"は不要。また、こちらはCVEではなく、JVN番号である
]

vectors_dict = {
	#Exploitability Metrics
	'AV': { #Access Vector
		'L': 'Local',
		'A': 'Adjacent Network',
		'N': 'Network'
	},
	'AC': { #Access Complexity
		'H': 'High',
		'M': 'Medium',
		'L': 'Low'
	},
	'Au': { #Authentication
		'M': 'Multiple',
		'S': 'Single',
		'N': 'None'
	},
	#Impact Metrics
	'C': { #Confidentially Impact
		'N': 'None',
		'P': 'Partial',
		'C': 'Complete'
	},
	'I': { #Integrity Impact
		'N': 'None',
		'P': 'Partial',
		'C': 'Complete'
	},
	'A': { #Availability Impact
		'N': 'None',
		'P': 'Partial',
		'C': 'Complete'
	}
}

def post_to_slack(webhook_url, msg, icon_url):
	payload = {
		"channel": "#jvn_alert",
		"username": "れんちょん❤️",
		"text": msg, #投稿するテキスト
		"icon_url": icon_url, #アイコン画像
	}
	jpayload = json.dumps(payload)
	res = requests.post(webhook_url, jpayload, headers={'Content-Type': 'application/json'})
	print("Response: {}".format(res))

def vector_calculator(vector):
	report = ""

	
	vectors = ['攻撃元区分', '攻撃条件の複雑さ', '攻撃前の認証要否', '機密性への影響', '完全性への影響', '可用性への影響']
	vector_values = vector[1:-1].split('/')
	for vector, vector_value in zip(vectors, vector_values):
		vector_value = vector_value.split(':')
		alert_emoji = ":bell:" if vectors_dict[vector_value[0]][vector_value[1]] == "Complete" else ""
		report += ">{vector}: *{vector_value}* {emoji}\n".format(vector=vector, vector_value=vectors_dict[vector_value[0]][vector_value[1]], emoji=alert_emoji)
	

	return report

def get_datetime(timestamp):
	year, month, day, hour, minute, second = re.findall(date_pat, timestamp)[0]
	return("{year}年{month}月{day}日 {hour}:{minute}:{second}".format(**locals()))

def getFaceChar():
	num = random.randint(0,839)
	f = open('./list.txt', 'r')
	face_char = f.readlines()[num]
	return face_char

def make_header():
	greet = ""
	greet += "にゃんぱす〜  {}\n".format(getFaceChar())
	greet += "今日も脆弱性報告するのんな〜\n"
	greet += "↓"*70 + "\n\n"

	return greet

#エントリーごとのメッセージ
def make_msg(index, entry, separator='-'):
	cve_id = entry['sec_references']['id']
	sec_id = entry['sec_identifier']

	alert = ""
	alert += "({index}) *{cve_id}* *{sec_id}*\n".format(index=index, cve_id=cve_id, sec_id=sec_id)

	alert += ">タイトル: *{title}*\n\n".format(title=entry['title'])
	alert += ">要約: \n>*{summary}  *\n\n\n\n".format(summary=entry['summary_detail']['value'])

	alert_emoji = ":bell:" if entry['sec_cvss']['severity'] == "High" else ""
	if alert_emoji == ":bell:":
		alert = ":bangbang: " + alert
	#レポート
	alert += "+"*10 + " 脆弱性評価レポート " + "+"*10 + "\n"
	alert += ">深刻度: *{severity}* {emoji}\n".format(severity=entry['sec_cvss']['severity'],emoji=alert_emoji)
	alert += ">評価点: *{score}*\n".format(score=entry['sec_cvss']['score'])
	alert += vector_calculator(entry['sec_cvss']['vector'])
	alert += "+"*36 + "\n\n"

	
	alert += "詳細については、以下のURLを参照してほしいのん。\n"
	for idx, link in enumerate(entry['links']):
		alert += ">JVNDB{idx}: {link}\n".format(idx=idx+1, link=link['href'])
	for idx, cve_db in enumerate(cve_dbs):
		alert += ">{idx}: ".format(idx=idx+1)
		alert += cve_db.format(cve_id=cve_id.replace('#', '')) + "\n"
	alert += "\n\nPublished({published}) ".format(published=get_datetime(entry['published']))
	alert += "Updated({updated})\n".format(updated=get_datetime(entry['updated']))
	
	alert += separator*180 + "\n\n\n"

	return alert

def make_footer():
	greet = ""
	greet += "\n"
	greet += "今日の報告は以上なんな〜\n"
	greet += "今日も１日がんばりますん！ :clap:\n"

	return greet

def make_whole_msg(entries, counts=50):
	if counts > len(entries):
		counts = len(entries)
	if counts == 0:
		return "No entries"

	whole_msg = ""
	whole_msg += make_header()

	for idx in range(counts):
		whole_msg += make_msg(idx+1, entries[idx])
	whole_msg += "Published by {publisher}.\n".format(publisher=publisher)
	whole_msg += make_footer()

	return whole_msg


d = feedparser.parse(url)
entries = d['entries']
try:
	publisher = d['entries'][0]['publisher']
except Exception as err:
	print(err)
	post_to_slack(webhook_url, "脆弱性情報さがしたのんに、見つからなったのん。今日は平和なのんな〜", icon_url)

result = make_whole_msg(entries)
print(result)
print("Posting...")
post_to_slack(webhook_url, result, icon_url)









