# football_checkin_bot.py

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request
import requests
import os
import re

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN")

# เก็บข้อมูลชั่วคราวในหน่วยความจำ
checked_in_users = {}
session_info = {"datetime": None, "location": None, "color": None, "created_by": None}

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    for event in data.get('events', []):

        if event['type'] == 'message':
            user_id = event['source']['userId']
            message_text = event['message']['text'].strip()
            message_text_lower = message_text.lower()

            if message_text_lower == 'remove':
                checked_in_users.clear()
                session_info.update({"datetime": None, "location": None, "color": None, "created_by": None})
                reply_text(event['replyToken'], "♻️ ข้อมูลทั้งหมดถึงรีเซ็ตเรียบร้อยแล้ว")
                continue

            if message_text_lower == 'repeat':
                if all(session_info.values()):
                    reply_flex_message(event['replyToken'])
                else:
                    reply_text(event['replyToken'], "⚠️ ยังไม่มี session ปัจจุบัน กรุณาพิมพ์ checkin เพื่อเริ่มใหม่")
                continue

            if message_text_lower == 'รายชื่อ':
                reply_text(event['replyToken'], get_checkin_message("📋 รายชื่อ"))
                continue

            if message_text_lower.startswith('@add'):
                name = message_text[4:].strip()
                if name:
                    synthetic_id = f"external_{len(checked_in_users)+1}"
                    checked_in_users[synthetic_id] = name
                    reply_text(event['replyToken'], f"✅ เพิ่ม {name} ในรายชื่อแล้ว\n\n" + get_checkin_message(name))
                else:
                    reply_text(event['replyToken'], "⚠️ กรุณาระบุชื่อหลังคำสั่ง @add เช่น @add สมชาย")
                continue

            if message_text_lower.startswith('@clear'):
                try:
                    index = int(message_text[6:].strip()) - 1
                    key_to_remove = list(checked_in_users.keys())[index]
                    name = checked_in_users.pop(key_to_remove)
                    reply_text(event['replyToken'], f"✅ ลบ {name} ออกจากรายชื่อแล้ว\n\n" + get_checkin_message("รายชื่อ"))
                except:
                    reply_text(event['replyToken'], "⚠️ รูปแบบคำสั่งไม่ถูกต้อง เช่น @clear 3 หรือลำดับไม่อยู่ในช่วงรายชื่อ")
                continue

            if message_text_lower.startswith('checkin'):
                session_info['created_by'] = user_id
                reply_datetime_input(event['replyToken'])

            elif user_id == session_info['created_by'] and validate_datetime_format(message_text):
                session_info['datetime'] = message_text
                reply_location_options(event['replyToken'])

            elif user_id == session_info['created_by'] and session_info['datetime'] is None:
                reply_text(event['replyToken'], "❌ รูปแบบไม่ถูกต้อง กรุณาพิมพ์ในรูปแบบ: DD/MM/YY 18:00")

        elif event['type'] == 'postback':
            user_id = event['source']['userId']
            profile = get_user_profile(user_id)
            display_name = profile.get('displayName') or f"UID:{user_id[-4:]}"
            action = event['postback']['data']

            if action.startswith('location=') and user_id == session_info['created_by']:
                session_info['location'] = action.split('=')[1]
                reply_color_options(event['replyToken'])

            elif action.startswith('color=') and user_id == session_info['created_by']:
                session_info['color'] = action.split('=')[1]
                reply_flex_message(event['replyToken'])

            elif action == 'action=checkin':
                if not all(session_info.values()):
                    reply_text(event['replyToken'], "⚠️ Session หมดอายุแล้ว กรุณาพิมพ์ checkin เพื่อเริ่มใหม่")
                    continue
                if user_id in checked_in_users:
                    continue
                checked_in_users[user_id] = display_name
                reply_text(event['replyToken'], get_checkin_message(display_name))

            elif action == 'action=request_cancel':
                if user_id in checked_in_users and not checked_in_users[user_id].endswith("(confirming)"):
                    checked_in_users[user_id] += " (confirming)"
                    reply_cancel_confirmation(event['replyToken'])
                elif user_id in checked_in_users:
                    reply_text(event['replyToken'], f"⚠️ {display_name} อยู่ระหว่างการยืนยันการยกเลิกแล้ว")
                else:
                    reply_text(event['replyToken'], f"⚠️ {display_name} ยังไม่ได้ลงชื่อ")

            elif action == 'action=confirm_cancel':
                if user_id in checked_in_users:
                    name = checked_in_users[user_id].replace(" (confirming)", "")
                    del checked_in_users[user_id]
                    reply_text(event['replyToken'], get_checkin_message(name))
                else:
                    reply_text(event['replyToken'], f"⚠️ {display_name} ยังไม่ได้ลงชื่อ")

            elif action == 'action=cancel':
                if user_id in checked_in_users and checked_in_users[user_id].endswith("(confirming)"):
                    checked_in_users[user_id] = checked_in_users[user_id].replace(" (confirming)", "")
                reply_text(event['replyToken'], "✅ ยกเลิกการยกเลิกแล้ว")

    return '', 200

def validate_datetime_format(text):
    return re.match(r'^\d{2}/\d{2}/\d{2} \d{2}:\d{2}$', text)

def get_color_emoji(color):
    return {
        'ดำ': '⚫️',
        'แดง': '🔴',
        'ขาว': '⚪️',
        'น้ำเงิน': '🔵'
    }.get(color, '👕')

def get_checkin_message(display_name):
    names = list(checked_in_users.values())
    name_list = "\n".join([f"{i+1}. {name}" for i, name in enumerate(names)])
    total = f"\n👥 จำนวนผู้ลงชื่อ: {len(names)} คน"
    color_emoji = get_color_emoji(session_info['color'])
    session = f"\n📆 วันเวลา: {session_info['datetime']}\n📍 สถานที่: {session_info['location']}\n{color_emoji} สีเสื้อ: {session_info['color']}" if all(session_info.values()) else ""
    return f"✅ {display_name} ลงชื่อเรียบร้อยแล้ว!{session}\n\n📋 รายชื่อที่ลงแล้ว:\n{name_list}{total}"

def reply_text(reply_token, text):
    headers = {
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    body = {
        "replyToken": reply_token,
        "messages": [
            {"type": "text", "text": text}
        ]
    }
    requests.post("https://api.line.me/v2/bot/message/reply", json=body, headers=headers)

def reply_datetime_input(reply_token):
    reply_text(reply_token, "📅 กรุณาพิมพ์วันเวลาในรูปแบบ: 26/05/68 18:00")

def reply_location_options(reply_token):
    headers = {
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    location_msg = {
        "type": "template",
        "altText": "เลือกสถานที่",
        "template": {
            "type": "buttons",
            "text": "เลือกสถานที่เตะบอล:",
            "actions": [
                {"type": "postback", "label": "LT", "data": "location=LT"},
                {"type": "postback", "label": "LP", "data": "location=LP"}
            ]
        }
    }
    body = {
        "replyToken": reply_token,
        "messages": [location_msg]
    }
    requests.post("https://api.line.me/v2/bot/message/reply", json=body, headers=headers)

def get_user_profile(user_id):
    headers = {"Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"}
    res = requests.get(f"https://api.line.me/v2/bot/profile/{user_id}", headers=headers)
    return res.json()

def reply_color_options(reply_token):
    headers = {
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    color_msg = {
        "type": "template",
        "altText": "เลือกสีเสื้อ",
        "template": {
            "type": "buttons",
            "text": "เลือกสีเสื้อ:",
            "actions": [
                {"type": "postback", "label": "ดำ", "data": "color=ดำ"},
                {"type": "postback", "label": "แดง", "data": "color=แดง"},
                {"type": "postback", "label": "ขาว", "data": "color=ขาว"},
                {"type": "postback", "label": "น้ำเงิน", "data": "color=น้ำเงิน"}
            ]
        }
    }
    body = {
        "replyToken": reply_token,
        "messages": [color_msg]
    }
    requests.post("https://api.line.me/v2/bot/message/reply", json=body, headers=headers)

def reply_flex_message(reply_token):
    headers = {
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    flex_msg = {
        "type": "flex",
        "altText": "ลงชื่อเตะบอล",
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": f"เตะบอล {session_info['datetime']} ที่ {session_info['location']} สีเสื้อ {session_info['color']}", "weight": "bold", "size": "lg"},
                    {
                        "type": "button",
                        "action": {"type": "postback", "label": "✅ ลงชื่อ", "data": "action=checkin"},
                        "style": "primary",
                        "margin": "md"
                    },
                    {
                        "type": "button",
                        "action": {"type": "postback", "label": "❌ ยกเลิกการลงชื่อ", "data": "action=request_cancel"},
                        "style": "secondary",
                        "margin": "md"
                    }
                ]
            }
        }
    }
    body = {
        "replyToken": reply_token,
        "messages": [flex_msg]
    }
    requests.post("https://api.line.me/v2/bot/message/reply", json=body, headers=headers)

def reply_cancel_confirmation(reply_token):
    headers = {
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    confirm_msg = {
        "type": "template",
        "altText": "ยืนยันการยกเลิก",
        "template": {
            "type": "confirm",
            "text": "คุณต้องการยกเลิกการลงชื่อหรือไม่?",
            "actions": [
                {"type": "postback", "label": "ยืนยัน", "data": "action=confirm_cancel"},
                {"type": "postback", "label": "ยกเลิก", "data": "action=cancel"}
            ]
        }
    }
    body = {
        "replyToken": reply_token,
        "messages": [confirm_msg]
    }
    requests.post("https://api.line.me/v2/bot/message/reply", json=body, headers=headers)

if __name__ == '__main__':
    app.run(port=3000)
