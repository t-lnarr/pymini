import asyncio
import logging
import json
import random
import os
from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    WebAppInfo
)
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# --- YAPILANDIRMA (Environment Variables) ---
API_TOKEN = os.getenv("BOT_TOKEN")

# Admin ID'lerini virgülle ayrılmış string olarak alıp listeye çeviriyoruz
admin_env = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x) for x in admin_env.split(",")] if admin_env else []

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- BELLEK İÇİ VERİ SAKLAMA ---
users_db = {}  # {user_id: {"username": str, "joined_date": str}}
quiz_stats = []  # [{"user_id": int, "is_correct": bool}, ...]

# --- VERİ YÖNETİMİ (Bellek Tabanlı) ---
async def add_user(user_id, username):
    if user_id not in users_db:
        users_db[user_id] = {
            "username": username,
            "joined_date": "now"
        }

async def get_all_users():
    return list(users_db.keys())

async def save_quiz_result(user_id, is_correct):
    quiz_stats.append({
        "user_id": user_id,
        "is_correct": is_correct
    })

async def get_stats():
    total_users = len(users_db)
    total_attempts = len(quiz_stats)
    correct_answers = sum(1 for stat in quiz_stats if stat["is_correct"])
    return total_users, total_attempts, correct_answers

# --- JSON SORU YÖNETİMİ ---
def load_questions():
    if not os.path.exists('questions.json'):
        return []
    with open('questions.json', 'r', encoding='utf-8') as f:
        return json.load(f)

# --- KLAVYE OLUŞTURUCU (Dinamik) ---
def get_main_keyboard(user_id):
    # Py mini butonu - Web App (Sohbet içinde açılır)
    web_app_url = f"https://telnarr.pythonanywhere.com/{user_id}"

    buttons = [
        [
            KeyboardButton(text="Py mini", web_app=WebAppInfo(url=web_app_url)),
            KeyboardButton(text="Quiz")
        ]
    ]

    # Eğer kullanıcı Admin ise, Admin butonunu ekle
    if user_id in ADMIN_IDS:
        buttons.append([KeyboardButton(text="⚙️ Admin")])

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, persistent=True)

# Admin Menü Klavyesi
admin_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="📢 Hemmä SMS")],
        [KeyboardButton(text="🔙 Asyl Menü")]
    ],
    resize_keyboard=True
)

# --- STATES ---
class AdminStates(StatesGroup):
    waiting_for_broadcast_message = State()

# --- HANDLERS ---
router = Router()

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    user = message.from_user
    await add_user(user.id, user.username)

    kb = get_main_keyboard(user.id)

    await message.answer(
        f"Salam {user.first_name}! Hoş geldin.\n"
        "Aşakdaky knopgalary ulanyp bilersiň.",
        reply_markup=kb
    )

@router.message(F.text == "Quiz")
async def process_quiz(message: types.Message):
    questions = load_questions()
    if not questions:
        await message.answer("Şu wagt sorag tapylanok.")
        return

    q_index = random.randint(0, len(questions) - 1)
    q_data = questions[q_index]
    options = q_data["cevaplar"]

    buttons = []
    for opt in options:
        buttons.append([
            InlineKeyboardButton(text=opt, callback_data=f"quiz:{q_index}:{opt}")
        ])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await message.answer(
        f"❓ **Sorag:**\n{q_data['soru']}",
        reply_markup=kb,
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("quiz:"))
async def check_quiz_answer(callback: CallbackQuery):
    try:
        _, q_index, user_answer = callback.data.split(":")
        q_index = int(q_index)

        questions = load_questions()
        if q_index >= len(questions):
            await callback.answer("Soragda näsazlyk çykdy.", show_alert=True)
            return

        correct_answer = questions[q_index]["dogru"]
        user_id = callback.from_user.id

        if user_answer == correct_answer:
            await save_quiz_result(user_id, True)
            await callback.answer("✅ Dogry jogap!", show_alert=True)
            await callback.message.edit_text(
                f"✅ **Dogry!**\n\nSorag: {questions[q_index]['soru']}\nJogabyň: {user_answer}",
                parse_mode="Markdown"
            )
        else:
            await save_quiz_result(user_id, False)
            await callback.answer(f"❌ Çalňyş. Dogrysy: {correct_answer}", show_alert=True)
            await callback.message.edit_text(
                f"❌ **Çalňyşşň!**\n\nSorag: {questions[q_index]['soru']}\nDogry Jogap: {correct_answer}",
                parse_mode="Markdown"
            )

    except Exception as e:
        logger.error(f"Quiz ýalňyşlygy: {e}")
        await callback.answer("Ýalňyşlyk bar.")

# --- ADMIN PANELİ ---

@router.message(Command("admin"))
@router.message(F.text == "⚙️ Admin")
async def cmd_admin(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    await message.answer("Admin panella.", reply_markup=admin_menu)

@router.message(F.text == "🔙 Asyl Menü")
async def back_to_main(message: types.Message):
    kb = get_main_keyboard(message.from_user.id)
    await message.answer("Ana menüye döndü.", reply_markup=kb)

@router.message(F.text == "📊 Statistika")
async def admin_stats(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    users, attempts, correct = await get_stats()
    ratio = (correct / attempts * 100) if attempts > 0 else 0

    stats_msg = (
        "📊 **Bot Statistika**\n\n"
        f"👥 Jemi Ulanyjy: `{users}`\n"
        f"📝 Çözülen Quiz: `{attempts}`\n"
        f"✅ Dogrylaň Sany: `{correct}`\n"
        f"📈 Üstünlik Prosent: `%{ratio:.2f}`"
    )
    await message.answer(stats_msg, parse_mode="Markdown")

@router.message(F.text == "📢 Hemmä SMS")
async def admin_broadcast_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return

    await message.answer(
        "Hemme ulanyjylara ugradyljak sms y ýazyň (Surat/Faýl bolup biler).\n"
        "Otkaz üçin 'iptal' ýazyň.",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await state.set_state(AdminStates.waiting_for_broadcast_message)

@router.message(AdminStates.waiting_for_broadcast_message)
async def process_broadcast(message: types.Message, state: FSMContext):
    if message.text and message.text.lower() == 'iptal':
        await state.clear()
        await message.answer("İptal edildi.", reply_markup=admin_menu)
        return

    users = await get_all_users()
    count = 0
    blocked = 0

    status_msg = await message.answer(f"Ugradylyp başlanýar... ({len(users)} kişi)")

    for uid in users:
        try:
            await message.copy_to(chat_id=uid)
            count += 1
            await asyncio.sleep(0.05)
        except Exception:
            blocked += 1

    await status_msg.edit_text(
        f"✅ Tamamlandy.\n\n"
        f"📨 Üstünlikli: {count}\n"
        f"🚫 Bolmady: {blocked}"
    )
    await message.answer("Admin paneli:", reply_markup=admin_menu)
    await state.clear()

# --- MAIN ---
async def main():
    if not API_TOKEN:
        print("HATA: BOT_TOKEN ayarlanmamış!")
        return

    bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    print("Bot bellek modunda çalışıyor...")

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot durduruldu.")
