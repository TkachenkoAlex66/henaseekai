from flask import Flask, render_template_string, request, jsonify, redirect
import uuid
import io
import os
import re
import base64  # <--- ДОБАВИЛ ДЛЯ РАСШИФРОВКИ КАРТИНКИ
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)

# ВСТАВЬ СЮДА СВОЙ КЛЮЧ АВТОРИЗАЦИИ ОТ GIGACHAT
GIGA_TOKEN = "MDFhMGMyY2MtOTZhMS03ZjE0LWFiNWYtMzBlMDE3NTBlYTc0OjM4OTMxNGM5LWZiZDYtNDk2ZS05ODc4LWFlMmZlMzFhY2E5NQ=="
APP_NAME = "henaseek AI"

if not os.path.exists('static/generated'):
    os.makedirs('static/generated')

chats_db = {}


# --- ФУНКЦИЯ, КОТОРАЯ РАСШИФРОВЫВАЕТ КАРТИНКУ ОТ СБЕРА ---
def add_watermark(image_input):
    try:
        img_bytes = None

        # 1. Достаем байты картинки из любого формата
        if isinstance(image_input, bytes):
            img_bytes = image_input
        elif hasattr(image_input, 'content'):
            # ЭТО ТА САМАЯ КОРОБОЧКА ОТ GIGACHAT
            content = image_input.content
            if isinstance(content, str):
                # Если внутри текст (Base64), расшифровываем его
                img_bytes = base64.b64decode(content)
            else:
                # Если уже байты, берем так
                img_bytes = content
        elif hasattr(image_input, 'read'):
            img_bytes = image_input.read()
        elif hasattr(image_input, 'save'):
            temp_io = io.BytesIO()
            image_input.save(temp_io, format='PNG')
            img_bytes = temp_io.getvalue()
        else:
            print(f"Неизвестный формат от GigaChat: {type(image_input)}")
            return None

        # 2. Открываем картинку и накладываем текст
        img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
        watermark = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(watermark)

        text = "henaseek AI"

        # Безопасная загрузка шрифта
        font = None
        for font_name in ["arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"]:
            try:
                font = ImageFont.truetype(font_name, 36)
                break
            except IOError:
                continue
        if font is None:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        margin = 15
        x = img.width - text_width - margin
        y = img.height - text_height - margin

        draw.text((x, y), text, font=font, fill=(255, 255, 255, 128))

        # 3. Сохраняем результат
        img = Image.alpha_composite(img, watermark)
        output = io.BytesIO()
        img.convert("RGB").save(output, format="JPEG", quality=95)
        return output.getvalue()

    except Exception as e:
        print(f"КРИТИЧЕСКАЯ ОШИБКА ВОДЯНОГО ЗНАКА: {e}")
        return None


# --- HTML ШАБЛОНЫ ---
BASE_HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>{{ app_name }}</title>
    <style>
        :root { --bg-main: #0d1117; --bg-sidebar: #161b22; --accent: #2ea043; --accent-hover: #3fb950; --text-main: #e6edf3; --text-muted: #8b949e; --border: #30363d; }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: var(--bg-main); color: var(--text-main); font-family: 'Segoe UI', Arial, sans-serif; display: flex; height: 100vh; overflow: hidden; }
        .sidebar { width: 260px; background: var(--bg-sidebar); border-right: 1px solid var(--border); display: flex; flex-direction: column; }
        .sidebar-header { padding: 20px; border-bottom: 1px solid var(--border); }
        .logo { font-size: 24px; font-weight: bold; color: var(--accent); margin-bottom: 20px; display: flex; align-items: center; gap: 10px;}
        .new-chat-btn { width: 100%; padding: 12px; background: var(--accent); color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; display: flex; justify-content: center; align-items: center; gap: 8px; transition: 0.2s; text-decoration: none; }
        .new-chat-btn:hover { background: var(--accent-hover); }
        .chat-list { flex: 1; overflow-y: auto; padding: 10px; }
        .chat-item { display: flex; justify-content: space-between; align-items: center; padding: 10px 15px; border-radius: 8px; cursor: pointer; color: var(--text-main); text-decoration: none; margin-bottom: 5px; transition: 0.2s; font-size: 14px; }
        .chat-item:hover { background: rgba(46, 160, 67, 0.1); }
        .chat-item.active { background: rgba(46, 160, 67, 0.2); border-left: 3px solid var(--accent); }
        .chat-title { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: 1; }
        .chat-actions { display: none; gap: 5px; }
        .chat-item:hover .chat-actions { display: flex; }
        .icon-btn { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 14px; padding: 2px; }
        .icon-btn:hover { color: var(--accent); }
        .main-content { flex: 1; display: flex; flex-direction: column; position: relative; }
        .welcome-screen { flex: 1; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; }
        .welcome-screen h1 { font-size: 48px; color: var(--accent); margin-bottom: 10px; }
        .welcome-screen p { color: var(--text-muted); font-size: 18px; margin-bottom: 20px;}
        .big-btn { padding: 15px 30px; background: var(--accent); color: white; text-decoration: none; border-radius: 10px; font-size: 18px; font-weight: bold; transition: 0.2s; }
        .big-btn:hover { background: var(--accent-hover); transform: scale(1.05); }
        .chat-container { flex: 1; overflow-y: auto; padding: 40px 10%; display: flex; flex-direction: column; gap: 20px; }
        .message { display: flex; gap: 15px; max-width: 800px; width: 100%; margin: 0 auto; }
        .avatar { width: 35px; height: 35px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; flex-shrink: 0; font-size: 18px; }
        .msg-user .avatar { background: #30363d; color: white; }
        .msg-bot .avatar { background: var(--accent); color: white; }
        .msg-content { line-height: 1.6; padding-top: 5px; max-width: 100%; }
        .msg-content img { max-width: 100%; border-radius: 8px; margin-top: 10px; border: 1px solid var(--border); }
        .input-area { padding: 20px 10%; background: var(--bg-main); }
        .input-box { max-width: 800px; margin: 0 auto; position: relative; background: var(--bg-sidebar); border: 1px solid var(--border); border-radius: 12px; display: flex; align-items: center; padding: 10px; }
        .input-box:focus-within { border-color: var(--accent); }
        input[type="text"] { flex: 1; background: none; border: none; color: white; padding: 10px 15px; font-size: 16px; outline: none; }
        .send-btn { background: var(--accent); color: white; border: none; border-radius: 8px; padding: 10px 15px; cursor: pointer; font-size: 18px; transition: 0.2s; }
        .send-btn:hover { background: var(--accent-hover); }
        .send-btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.7); display: none; justify-content: center; align-items: center; }
        .modal-content { background: var(--bg-sidebar); padding: 30px; border-radius: 15px; border: 1px solid var(--border); width: 400px; text-align: center; }
        .modal-content input { width: 100%; padding: 12px; margin: 15px 0; border-radius: 8px; border: 1px solid var(--border); background: var(--bg-main); color: white; }
        .modal-content button { padding: 10px 20px; border-radius: 8px; border: none; cursor: pointer; font-weight: bold; }
        .btn-save { background: var(--accent); color: white; margin-right: 10px; }
        .btn-cancel { background: #30363d; color: white; }
    </style>
</head>
<body>
    <div class="sidebar">
        <div class="sidebar-header">
            <div class="logo">🌿 {{ app_name }}</div>
            <a href="/chats/new/" class="new-chat-btn">+ Новый чат</a>
        </div>
        <div class="chat-list">
            {% for id, chat in chats.items() %}
                <div class="chat-item {% if id == current_id %}active{% endif %}">
                    <a href="/chats/chat/my/as/{{ id }}" style="color: inherit; text-decoration: none; flex: 1; overflow: hidden;">
                        <div class="chat-title">{{ chat.title }}</div>
                    </a>
                    <div class="chat-actions">
                        <button class="icon-btn" onclick="openRename('{{ id }}', '{{ chat.title }}')">✏️</button>
                        <button class="icon-btn" onclick="deleteChat('{{ id }}')">🗑️</button>
                    </div>
                </div>
            {% endfor %}
        </div>
    </div>
    <div class="main-content">
        {{ content|safe }}
    </div>
    <div class="modal-overlay" id="renameModal">
        <div class="modal-content">
            <h3>Переименовать чат</h3>
            <input type="text" id="newTitleInput">
            <button class="btn-save" onclick="saveRename()">Сохранить</button>
            <button class="btn-cancel" onclick="closeModal()">Отмена</button>
        </div>
    </div>
    <script>
        let chatToRename = null;
        function openRename(id, currentTitle) { chatToRename = id; document.getElementById('newTitleInput').value = currentTitle; document.getElementById('renameModal').style.display = 'flex'; }
        function closeModal() { document.getElementById('renameModal').style.display = 'none'; }
        async function saveRename() {
            const newTitle = document.getElementById('newTitleInput').value.trim();
            if (!newTitle) return;
            await fetch(`/api/rename/${chatToRename}`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({title: newTitle}) });
            location.reload();
        }
        async function deleteChat(id) {
            if (confirm('Ты уверен, что хочешь удалить этот чат?')) {
                await fetch(`/api/delete/${id}`, {method: 'DELETE'});
                if (window.location.pathname.includes(id)) { window.location.href = '/glavnya/'; } else { location.reload(); }
            }
        }
    </script>
</body>
</html>
"""

WELCOME_HTML = """
<div class="welcome-screen">
    <h1>{{ app_name }}</h1>
    <p>Твой личный помощник. Умею болтать и рисовать!</p>
    <a href="/chats/new/" class="big-btn">🚀 Начать общение</a>
</div>
"""

CHAT_HTML = """
<div class="chat-container" id="chat">
    {% for msg in messages %}
        <div class="message {{ 'msg-user' if msg.sender == 'user' else 'msg-bot' }}">
            <div class="avatar">{{ 'Т' if msg.sender == 'user' else '🌿' }}</div>
            <div class="msg-content">{{ msg.text|safe }}</div>
        </div>
    {% endfor %}
</div>
<div class="input-area">
    <div class="input-box">
        <input type="text" id="userInput" placeholder="Напиши сообщение или попроси нарисовать...">
        <button class="send-btn" id="sendBtn" onclick="send()">➤</button>
    </div>
</div>
<script>
    async function send() {
        const input = document.getElementById('userInput');
        const sendBtn = document.getElementById('sendBtn');
        const chat = document.getElementById('chat');
        const text = input.value.trim();
        if (!text) return;
        const userDiv = document.createElement('div');
        userDiv.className = 'message msg-user';
        userDiv.innerHTML = `<div class="avatar">Т</div><div class="msg-content">${text}</div>`;
        chat.appendChild(userDiv);
        input.value = '';
        sendBtn.disabled = true;
        chat.parentElement.scrollTop = chat.parentElement.scrollHeight;
        try {
            const res = await fetch('', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({message: text}) });
            const data = await res.json();
            const botDiv = document.createElement('div');
            botDiv.className = 'message msg-bot';
            const replyText = data.reply || "Ошибка: сервер не вернул ответ.";
            botDiv.innerHTML = `<div class="avatar">🌿</div><div class="msg-content">${replyText}</div>`;
            chat.appendChild(botDiv);
            chat.parentElement.scrollTop = chat.parentElement.scrollHeight;
        } catch (e) { alert("Ошибка соединения с сервером!"); } finally { sendBtn.disabled = false; }
    }
    document.getElementById('userInput').addEventListener('keypress', e => { if(e.key==='Enter') send(); });
</script>
"""


@app.route('/')
def start(): return redirect('/glavnya/')


@app.route('/glavnya/')
def glavnya(): return render_template_string(BASE_HTML, app_name=APP_NAME, chats=chats_db, current_id=None,
                                             content=render_template_string(WELCOME_HTML, app_name=APP_NAME))


@app.route('/chats/new/')
def new_chat():
    new_id = str(uuid.uuid4())
    chats_db[new_id] = {"title": "Новый чат", "messages": [{"sender": "bot",
                                                            "text": "Привет! Я henaseek, твой ИИ-помощник. Могу поболтать или нарисовать картинку. Чем могу помочь?"}]}
    return redirect(f'/chats/chat/my/as/{new_id}')


@app.route('/chats/chat/my/as/<chat_id>', methods=['GET', 'POST'])
def chat(chat_id):
    if chat_id not in chats_db: return redirect('/chats/chat/err/the/notfound??aserror&ichat?404&error')
    if request.method == 'POST':
        user_message = request.json.get('message')
        if len(chats_db[chat_id]['messages']) <= 1:
            new_title = user_message[:20] + ("..." if len(user_message) > 20 else "")
            chats_db[chat_id]['title'] = new_title
        chats_db[chat_id]['messages'].append({"sender": "user", "text": user_message})

        if GIGA_TOKEN == "ТВОЙ_КЛЮЧ_СЮДА" or not GIGA_TOKEN:
            bot_reply = "⚠️ Ключ GigaChat не установлен!"
        else:
            try:
                system_prompt = "Ты — henaseek AI, дружелюбный и умный помощник, созданный юным разработчиком по имени Женя. Ты никогда не должен упоминать Сбер, GigaChat, OpenAI или других разработчиков. Если тебя спросят, кто ты или кто тебя создал — гордо отвечай, что ты henaseek AI, и тебя сделал Женя. Общайся весело, дружелюбно и кратко."
                chat_payload = Chat(messages=[Messages(role=MessagesRole.SYSTEM, content=system_prompt),
                                              Messages(role=MessagesRole.USER, content=user_message)],
                                    function_call="auto")

                with GigaChat(credentials=GIGA_TOKEN, model="GigaChat-2", verify_ssl_certs=False) as giga:
                    response = giga.chat(chat_payload)
                    bot_reply = response.choices[0].message.content

                    img_match = re.search(r'<img src="([^"]+)"', bot_reply)
                    if img_match:
                        file_id = img_match.group(1)
                        image_data = giga.get_image(file_id)
                        watermarked = add_watermark(image_data)

                        if watermarked:
                            filename = f"{uuid.uuid4()}.jpg"
                            filepath = os.path.join('static/generated', filename)
                            with open(filepath, 'wb') as f:
                                f.write(watermarked)
                            bot_reply = f'<img src="/static/generated/{filename}">'
                        else:
                            bot_reply = "⚠️ Ошибка при обработке картинки. Посмотри консоль PyCharm."

            except Exception as e:
                bot_reply = f"⚠️ Ошибка GigaChat: {str(e)}"

        chats_db[chat_id]['messages'].append({"sender": "bot", "text": bot_reply})
        return jsonify({"reply": bot_reply})

    chat_content = render_template_string(CHAT_HTML, messages=chats_db[chat_id]['messages'])
    return render_template_string(BASE_HTML, app_name=APP_NAME, chats=chats_db, current_id=chat_id,
                                  content=chat_content)


@app.route('/api/rename/<chat_id>', methods=['POST'])
def rename_chat(chat_id):
    if chat_id in chats_db:
        new_title = request.json.get('title')
        if new_title:
            chats_db[chat_id]['title'] = new_title
            return jsonify({"status": "ok"})
    return jsonify({"status": "error"}), 400


@app.route('/api/delete/<chat_id>', methods=['DELETE'])
def delete_chat(chat_id):
    if chat_id in chats_db:
        del chats_db[chat_id]
        return jsonify({"status": "ok"})
    return jsonify({"status": "error"}), 404


@app.route('/chats/chat/err/the/notfound')
def err_notfound():
    error_content = '<div class="welcome-screen"><h1>404</h1><p>Этот чат не найден или был удален.</p><a href="/glavnya/" class="big-btn" style="font-size: 16px; padding: 10px 20px;">На главную</a></div>'
    return render_template_string(BASE_HTML, app_name=APP_NAME, chats=chats_db, current_id=None, content=error_content)


@app.route('/chats/chat/err/the/<nameerror>')
def err_custom(nameerror):
    code = request.args.get('ichat', 'Ошибка')
    error_content = f'<div class="welcome-screen"><h1>{code}</h1><p>Произошла ошибка: {nameerror}</p><a href="/glavnya/" class="big-btn" style="font-size: 16px; padding: 10px 20px;">На главную</a></div>'
    return render_template_string(BASE_HTML, app_name=APP_NAME, chats=chats_db, current_id=None, content=error_content)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)