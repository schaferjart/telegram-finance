# =================================================================================================
# Title: Telegram Finance Bot for Google Colab
# Description: This script sets up a personal finance tracking bot to run on Google Colab.
# Author: Your Name/Alias
# =================================================================================================

# @markdown # 1. Install Dependencies
# @markdown Run this cell to install the necessary Python libraries for the bot.
!pip install python-telegram-bot==20.3 -q

# =================================================================================================
# 2. Import Libraries
# =================================================================================================
# @markdown Import all the required libraries for the bot to function.
import json
import logging
import os
from datetime import datetime
from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, CallbackContext,
    ConversationHandler, CallbackQueryHandler,
)
import asyncio

# =================================================================================================
# 3. Configuration
# =================================================================================================
# @markdown # 3.1 Enter Your Bot Token
# @markdown Get your token by talking to [@BotFather](https://t.me/botfather) on Telegram.
TOKEN = 'YOUR_BOT_TOKEN'  # <--- PASTE YOUR TELEGRAM BOT TOKEN HERE

# @markdown # 3.2 Bot Settings (Optional)
# @markdown You can customize the bot's behavior and content below.

# --- TRANSACTION SETTINGS ---
CURRENCIES = ["USD", "EUR", "GBP"]
TRANSACTION_TYPES = ["groceries", "transport", "snack", "rent", "leisure"]
SPENDING_CATEGORIES = ["groceries", "transport", "snack", "rent", "leisure"]

# --- BOT BEHAVIOR ---
TRANSACTION_LIST_LIMIT = 15
CONVERSATION_TIMEOUT = 300  # 5 minutes
DATA_FILE = "finance_data.json"

# --- BUTTON LABELS ---
BTN_ADD_TRANSACTION = "Add Transaction"
BTN_LIST_TRANSACTIONS = "List Transactions"
BTN_GENERATE_REPORT = "Generate Report"
BTN_MANAGE_ACCOUNTS = "Manage Accounts"
BTN_CANCEL = "Cancel"
BTN_BACK = "Back"
BTN_YES = "Yes"
BTN_NONE = "None"

# --- MESSAGES ---
MSG_BOT_ACTIVE = "Finance Bot is active! What would you like to do?"
MSG_CANCELLED = "Operation cancelled. Returning to the main menu."
MSG_SESSION_TIMEOUT = "Session timed out. Returning to the main menu."
MSG_SELECT_TYPE = "What kind of transaction is this?"
MSG_ENTER_AMOUNT_SENT = "How much did you spend?"
MSG_SELECT_CURRENCY = "Select the currency:"
MSG_SELECT_FROM_ACCOUNT = "Which account did you use?"
MSG_ADD_INFO_QUESTION = "Do you want to add a note?"
MSG_ADD_INFO_DETAILS = "Please provide a short description for this transaction."
MSG_ENTER_INFO = "Enter the details now:"
MSG_ACCOUNTS_CURRENT = "Your accounts: {accounts}\n\nEnter a new name to add an account, or an existing name to remove it."
MSG_ACCOUNTS_EMPTY = "You have no accounts. Enter a name to create one."
MSG_ACCOUNTS_CLOSED = "Account management closed."
MSG_ACCOUNT_REMOVED = "Account '{account}' has been removed."
MSG_ACCOUNT_ADDED = "Account '{account}' has been added."
MSG_NO_ACCOUNTS = "You don't have any accounts yet."
MSG_USE_MANAGE_ACCOUNTS = "Please set up an account first using the 'Manage Accounts' button."
MSG_INVALID_AMOUNT = "That's not a valid amount. Please enter a number (e.g., 10.50)."
MSG_NO_TRANSACTIONS = "No transactions found."
MSG_TRANSACTION_ADDED_SIMPLE = "✅ Transaction Recorded!\n\nType: {type}\nAmount: {amount} {currency}\nAccount: {account}\nNotes: {info}"

# --- REPORTING ---
REPORT_HEADER_TRANSACTIONS = "📄 Your Recent Transactions:"
REPORT_HEADER_LOG = "📋 Full Transaction Log"
REPORT_HEADER_ACCOUNTS = "💳 Account Summary"
REPORT_HEADER_SPENDING = "📊 Spending by Category"
REPORT_BALANCE_SETTLED = "Confirmed Balance"
DESC_TEMPLATE_SIMPLE = "{type} purchase"
TABLE_HEADER = "| Date | Type | Amount | Curr | From | Details |"
TABLE_SEPARATOR = "|---|---|---|---|---|---|"

# =================================================================================================
# 4. Bot Logic
# =================================================================================================
# @markdown This section contains the core logic of the bot.

# --- LOGGING SETUP ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- DATA HANDLING ---
def load_data():
    try:
        with open(DATA_FILE, "r") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"transactions": [], "accounts": [], "balances": {}, "spending_categories": {}}

def save_data(data):
    with open(DATA_FILE, "w") as file:
        json.dump(data, file, indent=4)

# --- KEYBOARDS ---
CB_FROM_PREFIX = "from:"
CB_TYPE_PREFIX = "type:"
CB_CURRENCY_SENT_PREFIX = "curr_sent:"
CB_INFO_PREFIX = "info:"

TRANS_TYPE, TRANS_AMOUNT_SENT, TRANS_CURRENCY_SENT, TRANS_FROM, TRANS_INFO = range(5)
MANAGE_ACCOUNT, = range(1)

def get_main_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton(BTN_ADD_TRANSACTION), KeyboardButton(BTN_LIST_TRANSACTIONS)],
         [KeyboardButton(BTN_GENERATE_REPORT), KeyboardButton(BTN_MANAGE_ACCOUNTS)],
         [KeyboardButton(BTN_CANCEL)]],
        resize_keyboard=True
    )

def build_inline_kb(prefix, options):
    return InlineKeyboardMarkup([[InlineKeyboardButton(opt, callback_data=f"{prefix}{opt}")] for opt in options])

# --- CORE FUNCTIONS ---
async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(MSG_BOT_ACTIVE, reply_markup=get_main_keyboard())

async def manage_accounts(update: Update, context: CallbackContext):
    accounts = load_data().get("accounts", [])
    msg = MSG_ACCOUNTS_CURRENT.format(accounts=", ".join(accounts)) if accounts else MSG_ACCOUNTS_EMPTY
    await update.message.reply_text(msg, reply_markup=ReplyKeyboardMarkup([[BTN_BACK]], resize_keyboard=True))
    return MANAGE_ACCOUNT

async def modify_accounts(update: Update, context: CallbackContext):
    data = load_data()
    text = update.message.text.strip()
    if text.lower() == BTN_BACK.lower():
        await update.message.reply_text(MSG_ACCOUNTS_CLOSED, reply_markup=get_main_keyboard())
        return ConversationHandler.END

    if text in data["accounts"]:
        data["accounts"].remove(text)
        data["balances"].pop(text, None)
        response = MSG_ACCOUNT_REMOVED.format(account=text)
    else:
        data["accounts"].append(text)
        data["balances"][text] = {"settled": {}}
        response = MSG_ACCOUNT_ADDED.format(account=text)

    save_data(data)
    await update.message.reply_text(response, reply_markup=get_main_keyboard())
    return ConversationHandler.END

async def start_transaction(update: Update, context: CallbackContext):
    context.user_data.clear()
    await update.message.reply_text(MSG_SELECT_TYPE, reply_markup=build_inline_kb(CB_TYPE_PREFIX, TRANSACTION_TYPES))
    return TRANS_TYPE

async def trans_type_cb(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    context.user_data["type"] = query.data[len(CB_TYPE_PREFIX):]
    await query.edit_message_text(MSG_ENTER_AMOUNT_SENT)
    return TRANS_AMOUNT_SENT

async def trans_amount_sent(update: Update, context: CallbackContext):
    try:
        context.user_data["amount_sent"] = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text(MSG_INVALID_AMOUNT)
        return TRANS_AMOUNT_SENT
    await update.message.reply_text(MSG_SELECT_CURRENCY, reply_markup=build_inline_kb(CB_CURRENCY_SENT_PREFIX, CURRENCIES))
    return TRANS_CURRENCY_SENT

async def trans_currency_sent_cb(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    context.user_data["currency_sent"] = query.data[len(CB_CURRENCY_SENT_PREFIX):]
    accounts = load_data().get("accounts", [])
    if not accounts:
        await query.edit_message_text(MSG_NO_ACCOUNTS)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=MSG_USE_MANAGE_ACCOUNTS, reply_markup=get_main_keyboard())
        return ConversationHandler.END
    await query.edit_message_text(MSG_SELECT_FROM_ACCOUNT)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=MSG_SELECT_FROM_ACCOUNT, reply_markup=build_inline_kb(CB_FROM_PREFIX, accounts))
    return TRANS_FROM

async def trans_from_cb(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    context.user_data["from"] = query.data[len(CB_FROM_PREFIX):]
    await query.edit_message_text(MSG_ADD_INFO_QUESTION)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=MSG_ADD_INFO_DETAILS, reply_markup=build_inline_kb(CB_INFO_PREFIX, [BTN_YES, BTN_NONE]))
    return TRANS_INFO

async def trans_info_cb(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    if query.data.endswith(BTN_NONE):
        context.user_data["info"] = ""
        return await finalize_transaction(update, context)
    await query.edit_message_text(MSG_ENTER_INFO)
    return TRANS_INFO

async def trans_info_text(update: Update, context: CallbackContext):
    context.user_data["info"] = update.message.text.strip()
    return await finalize_transaction(update, context)

async def finalize_transaction(update, context):
    data = load_data()
    user_data = context.user_data
    trans = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "type": user_data["type"],
        "amount_sent": user_data["amount_sent"],
        "currency_sent": user_data["currency_sent"],
        "from": user_data["from"],
        "info": user_data.get("info", ""),
        "amount_received": 0, "currency_received": "", "to": "", "status": "closed",
        "description": DESC_TEMPLATE_SIMPLE.format(type=user_data["type"].capitalize())
    }
    data["transactions"].append(trans)

    # Update balances
    from_acc, sent_curr, sent_amt = trans["from"], trans["currency_sent"], trans["amount_sent"]
    if from_acc not in data["balances"]: data["balances"][from_acc] = {"settled": {}}
    data["balances"][from_acc]["settled"][sent_curr] = data["balances"][from_acc]["settled"].get(sent_curr, 0) - sent_amt

    # Update spending
    trans_type = trans["type"]
    if trans_type in SPENDING_CATEGORIES:
        cat = data["spending_categories"].get(trans_type, {"transactions": [], "total": {}})
        cat["transactions"].append(trans)
        cat["total"][sent_curr] = cat["total"].get(sent_curr, 0) + sent_amt
        data["spending_categories"][trans_type] = cat

    save_data(data)
    response_msg = MSG_TRANSACTION_ADDED_SIMPLE.format(
        type=trans['type'].capitalize(), date=trans['date'], amount=trans['amount_sent'],
        currency=trans['currency_sent'], account=trans['from'], info=trans['info'] or 'N/A'
    )

    # Send confirmation
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.message.reply_text(response_msg, reply_markup=get_main_keyboard())
    else:
        await update.message.reply_text(response_msg, reply_markup=get_main_keyboard())
    return ConversationHandler.END

async def list_transactions(update: Update, context: CallbackContext):
    transactions = load_data().get("transactions", [])
    if not transactions:
        await update.message.reply_text(MSG_NO_TRANSACTIONS, reply_markup=get_main_keyboard())
        return

    lines = [f"{REPORT_HEADER_TRANSACTIONS}\n", f"```{TABLE_HEADER}", TABLE_SEPARATOR]
    for t in transactions[-TRANSACTION_LIST_LIMIT:][::-1]:
        lines.append(f"| {t['date']} | {t['type']} | {t['amount_sent']} | {t['currency_sent']} | {t['from']} | {t.get('info', '')[:10]} |")
    lines.append("```")
    await update.message.reply_text("\n".join(lines), parse_mode='MarkdownV2')

async def generate_report(update: Update, context: CallbackContext):
    data = load_data()
    # Simplified report for Colab version
    report = f"**{REPORT_HEADER_ACCOUNTS}**\n"
    for acc, balances in data.get("balances", {}).items():
        settled = ", ".join([f"{amt:.2f} {curr}" for curr, amt in balances.get("settled", {}).items()])
        report += f" - **{acc}**: {settled or '0.00'}\n"

    report += f"\n**{REPORT_HEADER_SPENDING}**\n"
    for cat, details in data.get("spending_categories", {}).items():
        totals = ", ".join([f"{amt:.2f} {curr}" for curr, amt in details.get("total", {}).items()])
        report += f" - **{cat.capitalize()}**: {totals or '0.00'}\n"

    await update.message.reply_text(report, reply_markup=get_main_keyboard(), parse_mode='Markdown')

async def cancel(update: Update, context: CallbackContext):
    await update.message.reply_text(MSG_CANCELLED, reply_markup=get_main_keyboard())
    return ConversationHandler.END

async def on_timeout(update: Update, context: CallbackContext):
    await context.bot.send_message(chat_id=update.effective_chat.id, text=MSG_SESSION_TIMEOUT, reply_markup=get_main_keyboard())

# =================================================================================================
# 5. Run the Bot
# =================================================================================================
# @markdown ## Run this cell to start your bot!
# @markdown Your bot will start polling for messages. You can stop it by interrupting the kernel.

async def main():
    if TOKEN == 'YOUR_BOT_TOKEN':
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print("!!! ERROR: Please paste your bot token in the section 3.1 !!!")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        return

    app = Application.builder().token(TOKEN).build()

    # Conversation Handlers
    trans_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f"^{BTN_ADD_TRANSACTION}$"), start_transaction)],
        states={
            TRANS_TYPE: [CallbackQueryHandler(trans_type_cb, pattern=f"^{CB_TYPE_PREFIX}")],
            TRANS_AMOUNT_SENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, trans_amount_sent)],
            TRANS_CURRENCY_SENT: [CallbackQueryHandler(trans_currency_sent_cb, pattern=f"^{CB_CURRENCY_SENT_PREFIX}")],
            TRANS_FROM: [CallbackQueryHandler(trans_from_cb, pattern=f"^{CB_FROM_PREFIX}")],
            TRANS_INFO: [
                CallbackQueryHandler(trans_info_cb, pattern=f"^{CB_INFO_PREFIX}"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, trans_info_text)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(filters.Regex(f"^{BTN_CANCEL}$"), cancel)],
        conversation_timeout=CONVERSATION_TIMEOUT,
        per_message=False,
    )
    manage_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f"^{BTN_MANAGE_ACCOUNTS}$"), manage_accounts)],
        states={MANAGE_ACCOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, modify_accounts)]},
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(filters.Regex(f"^{BTN_CANCEL}$"), cancel)],
        conversation_timeout=CONVERSATION_TIMEOUT,
        per_message=False,
    )

    app.add_handler(trans_conv)
    app.add_handler(manage_conv)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_LIST_TRANSACTIONS}$"), list_transactions))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_GENERATE_REPORT}$"), generate_report))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_CANCEL}$"), cancel))

    print("Bot is running... Press the stop button in Colab to quit.")
    await app.run_polling()

# This is the standard way to run an asyncio program in a script.
# In a notebook, you would typically just call `await main()` in a cell.
if __name__ == '__main__':
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        print("Bot is already running in an asyncio loop.")
        # If you want to run it again, you might need to stop the previous one first.
        # loop.create_task(main())
    else:
        asyncio.run(main())
