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
sessions = []  # รองรับหลาย session
checked_in_users = {}  # mapping: session_id -> { user_id: display_name }

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    for event in data.get('events', []):

        if event['type'] == 'message':
            user_id = event['source']['userId']
            message_text = event['message']['text'].strip().lower()

            if message_text == 'remove':
                sessions.clear()
                checked_in_users.clear()
                reply_text(event['replyToken'], "♻️ ข้อมูลทั้งหมดถึงรีเซ็ตเรียบร้อยแล้ว")
                continue

            if message_text == 'repeat':
                if sessions:
                    reply_flex_message(event['replyToken'], sessions[-1])
                else:
                    reply_text(event['replyToken'], "❌ ยังไม่มีการ Checkin กรุณาพิมพ์ checkin เพื่อเริ่มใหม่")
                continue

            if message_text == 'รายชื่อ':
                if sessions:
                    reply_text(event['replyToken'], get_checkin_message(sessions[-1]))
                else:
                    reply_text(event['replyToken'], "📋 ยังไม่มี session ที่เปิดอยู่")
                continue

            if message_text.startswith('checkin'):
                session = {"datetime": None, "location": None, "color": None, "created_by": user_id}
                sessions.append(session)
                checked_in_users[id(session)] = {}
                reply_datetime_input(event['replyToken'])

            elif sessions and user_id == sessions[-1]['created_by'] and validate_datetime_format(message_text):
                sessions[-1]['datetime'] = message_text
                reply_location_options(event['replyToken'])

            elif sessions and user_id == sessions[-1]['created_by'] and sessions[-1]['datetime'] is None:
                reply_text(event['replyToken'], "❌ รูปแบบไม่ถูกต้อง กรุณาพิมพ์ในรูปแบบ: 26/05/68 18:00")

        elif event['type'] == 'postback' and sessions:
            session = sessions[-1]
            user_id = event['source']['userId']
            profile = get_user_profile(user_id)
            display_name = profile.get('displayName') or f"UID:{user_id[-4:]}"
            action = event['postback']['data']

            if action.startswith('location=') and user_id == session['created_by']:
                session['location'] = action.split('=')[1]
                reply_color_options(event['replyToken'])

            elif action.startswith('color=') and user_id == session['created_by']:
                session['color'] = action.split('=')[1]
                reply_flex_message(event['replyToken'], session)

            elif action == 'action=checkin':
                if user_id in checked_in_users[id(session)]:
                    continue
                checked_in_users[id(session)][user_id] = display_name
                reply_text(event['replyToken'], get_checkin_message(session))

            elif action == 'action=request_cancel':
                if user_id in checked_in_users[id(session)]:
                    reply_cancel_confirmation(event['replyToken'])
                else:
                    reply_text(event['replyToken'], f"⚠️ {display_name} ยังไม่ได้ลงชื่อ")

            elif action == 'action=confirm_cancel':
                if user_id in checked_in_users[id(session)]:
                    del checked_in_users[id(session)][user_id]
                    reply_text(event['replyToken'], get_checkin_message(session))
                else:
                    reply_text(event['replyToken'], f"⚠️ {display_name} ยังไม่ได้ลงชื่อ")

            elif action == 'action=cancel':
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

def get_checkin_message(session):
    users = list(checked_in_users.get(id(session), {}).values())
    name_list = "\n".join([f"{i+1}. {name}" for i, name in enumerate(users)])
    total = f"\n👥 จำนวนผู้ลงชื่อ: {len(users)} คน"
    color_emoji = get_color_emoji(session['color'])
    session_text = f"\n📆 วันเวลา: {session['datetime']}\n📍 สถานที่: {session['location']}\n{color_emoji} สีเสื้อ: {session['color']}" if all(session.values()) else ""
    return f"📋 รายชื่อที่ลงแล้ว:{session_text}\n\n{name_list}{total}"

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

def reply_flex_message(reply_token, session):
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
                    {"type": "text", "text": f"เตะบอล {session['datetime']} ที่ {session['location']} สีเสื้อ {session['color']}", "weight": "bold", "size": "lg"},
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
