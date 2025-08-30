import json
import logging
import os
from datetime import datetime, timedelta
import markdown2
import weasyprint

from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, CallbackContext,
    ConversationHandler, CallbackQueryHandler,
)
from telegram.error import TelegramError

from markdown2 import markdown
from weasyprint import HTML

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Import all config variables
try:
    from config import (
        TOKEN, BOT_HANDLER_ID, CURRENCIES, TRANSACTION_TYPES, TRANSACTION_STATUSES,
        SIMPLE_TRANSACTION_TYPES, SPENDING_CATEGORIES, TRANSACTION_LIST_LIMIT,
        CONVERSATION_TIMEOUT, HEARTBEAT_INTERVAL_HOURS, DATA_FILE,
        BTN_ADD_TRANSACTION, BTN_LIST_TRANSACTIONS, BTN_GENERATE_REPORT,
        BTN_MANAGE_ACCOUNTS, BTN_DELETE_ALL_DATA, BTN_GENERATE_IMAGE_REPORT, BTN_CANCEL, BTN_BACK, BTN_DONE,
        BTN_YES, BTN_NONE, MSG_BOT_ACTIVE, MSG_CANCELLED, MSG_SESSION_TIMEOUT,
        MSG_SELECT_TYPE, MSG_ENTER_AMOUNT_SENT, MSG_SELECT_CURRENCY,
        MSG_SELECT_FROM_ACCOUNT, MSG_ENTER_AMOUNT_RECEIVED, MSG_SELECT_CURRENCY_RECEIVED,
        MSG_SELECT_TO_ACCOUNT, MSG_SELECT_STATUS, MSG_ADD_INFO_QUESTION,
        MSG_ADD_INFO_DETAILS, MSG_ENTER_INFO, MSG_ACCOUNTS_CURRENT, MSG_ACCOUNTS_EMPTY,
        MSG_ACCOUNTS_CLOSED, MSG_ACCOUNT_REMOVED, MSG_ACCOUNT_ADDED, MSG_NO_ACCOUNTS,
        MSG_USE_MANAGE_ACCOUNTS, MSG_INVALID_AMOUNT, MSG_INVALID_AMOUNT_RECEIVED,
        MSG_NO_TRANSACTIONS, MSG_TRANSACTION_ADDED_SIMPLE, MSG_TRANSACTION_ADDED_FULL,
        MSG_CONFIRM_DELETE, MSG_DATA_DELETED, MSG_DELETE_CANCELLED, CONFIRM_DELETE_TEXT,
        REPORT_HEADER_TRANSACTIONS, REPORT_HEADER_LOG, REPORT_HEADER_ACCOUNTS,
        REPORT_HEADER_SPENDING, REPORT_BALANCE_SETTLED, REPORT_BALANCE_PENDING,
        DESC_TEMPLATE_SIMPLE, DESC_TEMPLATE_COMPLEX, TABLE_HEADER, TABLE_SEPARATOR,
        TABLE_HEADER_FULL
    )
except ImportError as e:
    print(f"Error: config.py file not found or incomplete! Missing: {e}")
    print("Please ensure all required variables are defined in config.py")
    exit(1)

# Validate token
if not TOKEN or TOKEN == "YOUR_ACTUAL_BOT_TOKEN":
    print("Error: Please set your actual bot token in config.py")
    print("Get a token from @BotFather on Telegram")
    exit(1)


def load_data():
    try:
        with open(DATA_FILE, "r") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        default_data = {"transactions": [], "accounts": [], "balances": {}, "spending_categories": {}}
        with open(DATA_FILE, "w") as file:
            json.dump(default_data, file, indent=4)
        return default_data


def save_data(data):
    with open(DATA_FILE, "w") as file:
        json.dump(data, file, indent=4)


# Callback data prefixes
CB_FROM_PREFIX = "from:"
CB_TO_PREFIX = "to:"
CB_TYPE_PREFIX = "type:"
CB_STATUS_PREFIX = "status:"
CB_CURRENCY_SENT_PREFIX = "curr_sent:"
CB_CURRENCY_RECEIVED_PREFIX = "curr_recv:"
CB_INFO_PREFIX = "info:"
CB_DONE = "done"
CB_BACK = "back"
CB_CANCEL = "cancel"
CB_DELETE_ALL = "delete_all"

# States for conversation handler
TRANS_TYPE, TRANS_AMOUNT_SENT, TRANS_CURRENCY_SENT, TRANS_FROM, \
TRANS_AMOUNT_RECEIVED, TRANS_CURRENCY_RECEIVED, TRANS_TO, TRANS_STATUS, TRANS_INFO = range(9)
MANAGE_ACCOUNT, CONFIRM_DELETE = range(2)


# Dynamic Keyboards
def get_main_keyboard():
    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton(BTN_ADD_TRANSACTION),
                KeyboardButton(BTN_LIST_TRANSACTIONS),
            ],
            [
                KeyboardButton(BTN_GENERATE_REPORT),
                KeyboardButton(BTN_MANAGE_ACCOUNTS),
            ],
            [
                KeyboardButton(BTN_DELETE_ALL_DATA),
                KeyboardButton(BTN_CANCEL),
            ],
            [KeyboardButton(BTN_GENERATE_IMAGE_REPORT)
            ]
        ],
        resize_keyboard=True,
    )


def get_account_keyboard(data):
    accounts = data.get("accounts", [])
    if not accounts:
        return None
    buttons = [[KeyboardButton(account)] for account in accounts]
    buttons.append([KeyboardButton(BTN_DONE)])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


def build_inline_kb(prefix, options):
    rows = [[InlineKeyboardButton(opt, callback_data=f"{prefix}{opt}")] for opt in options]
    return InlineKeyboardMarkup(rows)


def build_type_inline_kb():
    return build_inline_kb(CB_TYPE_PREFIX, TRANSACTION_TYPES)


def build_status_inline_kb():
    return build_inline_kb(CB_STATUS_PREFIX, TRANSACTION_STATUSES)


def build_currency_inline_kb(prefix):
    return build_inline_kb(prefix, CURRENCIES)


def build_info_inline_kb():
    options = [BTN_YES, BTN_NONE]
    return build_inline_kb(CB_INFO_PREFIX, options)


def build_delete_confirmation_kb():
    options = [BTN_YES, BTN_CANCEL]
    return build_inline_kb(CB_DELETE_ALL, options)


async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text(
        MSG_BOT_ACTIVE, reply_markup=get_main_keyboard()
    )


# Delete All Data
async def delete_all_data(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text(
        MSG_CONFIRM_DELETE,
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton(BTN_BACK)]], resize_keyboard=True),
    )
    return CONFIRM_DELETE


async def confirm_delete(update: Update, context: CallbackContext) -> int:
    text = update.message.text.strip()
    if text == CONFIRM_DELETE_TEXT:
        # Delete all data
        default_data = {"transactions": [], "accounts": [], "balances": {}, "spending_categories": {}}
        save_data(default_data)
        await update.message.reply_text(
            MSG_DATA_DELETED, reply_markup=get_main_keyboard()
        )
    elif text.lower() == BTN_BACK.lower():
        await update.message.reply_text(
            MSG_DELETE_CANCELLED, reply_markup=get_main_keyboard()
        )
    else:
        await update.message.reply_text(
            MSG_DELETE_CANCELLED, reply_markup=get_main_keyboard()
        )
    return ConversationHandler.END


# Manage Accounts
async def manage_accounts(update: Update, context: CallbackContext) -> int:
    data = load_data()
    if data["accounts"]:
        accounts_list = ", ".join(data["accounts"])
        txt = MSG_ACCOUNTS_CURRENT.format(accounts=accounts_list)
    else:
        txt = MSG_ACCOUNTS_EMPTY

    await update.message.reply_text(
        txt,
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton(BTN_BACK)]], resize_keyboard=True),
    )
    return MANAGE_ACCOUNT


async def modify_accounts(update: Update, context: CallbackContext) -> int:
    data = load_data()
    text = update.message.text.strip()
    if text.lower() == BTN_BACK.lower():
        await update.message.reply_text(
            MSG_ACCOUNTS_CLOSED, reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

    name_ci = text.lower()
    existing_index = next(
        (i for i, m in enumerate(data["accounts"]) if m.lower() == name_ci), None
    )
    if existing_index is not None:
        removed = data["accounts"].pop(existing_index)
        # Also remove from balances if exists
        data["balances"].pop(removed, None)
        response = MSG_ACCOUNT_REMOVED.format(account=removed)
    else:
        data["accounts"].append(text)
        data["balances"][text] = {"settled": {}, "pending": {}}
        response = MSG_ACCOUNT_ADDED.format(account=text)

    save_data(data)
    await update.message.reply_text(response, reply_markup=get_main_keyboard())
    return ConversationHandler.END


# Transaction flow
async def start_transaction(update: Update, context: CallbackContext) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        MSG_SELECT_TYPE, 
        reply_markup=build_type_inline_kb()
    )
    return TRANS_TYPE


async def trans_type_cb(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    if query.data.startswith(CB_TYPE_PREFIX):
        trans_type = query.data[len(CB_TYPE_PREFIX):]
        context.user_data["type"] = trans_type
        
        # Set defaults for simple transaction types
        if trans_type in SIMPLE_TRANSACTION_TYPES:
            context.user_data["amount_received"] = 0.0
            context.user_data["currency_received"] = ""
            context.user_data["to"] = ""
            context.user_data["status"] = "closed"
        
        await query.edit_message_text(MSG_ENTER_AMOUNT_SENT)
        return TRANS_AMOUNT_SENT
    return TRANS_TYPE


async def trans_amount_sent(update: Update, context: CallbackContext) -> int:
    try:
        context.user_data["amount_sent"] = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text(MSG_INVALID_AMOUNT)
        return TRANS_AMOUNT_SENT
    
    await update.message.reply_text(
        MSG_SELECT_CURRENCY, 
        reply_markup=build_currency_inline_kb(CB_CURRENCY_SENT_PREFIX)
    )
    return TRANS_CURRENCY_SENT


async def trans_currency_sent_cb(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    if query.data.startswith(CB_CURRENCY_SENT_PREFIX):
        currency = query.data[len(CB_CURRENCY_SENT_PREFIX):]
        context.user_data["currency_sent"] = currency
        
        data = load_data()
        if not data.get("accounts"):
            await query.edit_message_text(MSG_NO_ACCOUNTS)
            await update.callback_query.message.reply_text(
                MSG_USE_MANAGE_ACCOUNTS,
                reply_markup=get_main_keyboard()
            )
            return ConversationHandler.END
            
        await query.edit_message_text(MSG_SELECT_FROM_ACCOUNT)
        await update.callback_query.message.reply_text(
            MSG_SELECT_FROM_ACCOUNT, 
            reply_markup=build_inline_kb(CB_FROM_PREFIX, data["accounts"])
        )
        return TRANS_FROM
    return TRANS_CURRENCY_SENT


async def trans_from_cb(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    if query.data.startswith(CB_FROM_PREFIX):
        from_acc = query.data[len(CB_FROM_PREFIX):]
        context.user_data["from"] = from_acc
        
        trans_type = context.user_data.get("type")
        
        # For simple transaction types, skip to info step
        if trans_type in SIMPLE_TRANSACTION_TYPES:
            await query.edit_message_text(MSG_ADD_INFO_QUESTION)
            await update.callback_query.message.reply_text(
                MSG_ADD_INFO_DETAILS,
                reply_markup=build_info_inline_kb()
            )
            return TRANS_INFO
        
        # For other transactions, continue normal flow
        await query.edit_message_text(MSG_ENTER_AMOUNT_RECEIVED)
        return TRANS_AMOUNT_RECEIVED
    return TRANS_FROM


async def trans_amount_received(update: Update, context: CallbackContext) -> int:
    try:
        amount_received = float(update.message.text.replace(",", "."))
        context.user_data["amount_received"] = amount_received
        
        # If amount is 0, skip currency and account selection
        if amount_received == 0:
            context.user_data["currency_received"] = ""
            context.user_data["to"] = context.user_data["from"]  # Same account
            await update.message.reply_text(
                MSG_SELECT_STATUS, 
                reply_markup=build_status_inline_kb()
            )
            return TRANS_STATUS
        else:
            await update.message.reply_text(
                MSG_SELECT_CURRENCY_RECEIVED, 
                reply_markup=build_currency_inline_kb(CB_CURRENCY_RECEIVED_PREFIX)
            )
            return TRANS_CURRENCY_RECEIVED
            
    except ValueError:
        await update.message.reply_text(MSG_INVALID_AMOUNT_RECEIVED)
        return TRANS_AMOUNT_RECEIVED


async def trans_currency_received_cb(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    if query.data.startswith(CB_CURRENCY_RECEIVED_PREFIX):
        currency = query.data[len(CB_CURRENCY_RECEIVED_PREFIX):]
        context.user_data["currency_received"] = currency
        
        data = load_data()
        await query.edit_message_text(MSG_SELECT_TO_ACCOUNT)
        await update.callback_query.message.reply_text(
            MSG_SELECT_TO_ACCOUNT, 
            reply_markup=build_inline_kb(CB_TO_PREFIX, data["accounts"])
        )
        return TRANS_TO
    return TRANS_CURRENCY_RECEIVED


async def trans_to_cb(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    if query.data.startswith(CB_TO_PREFIX):
        to_acc = query.data[len(CB_TO_PREFIX):]
        context.user_data["to"] = to_acc
        await query.edit_message_text(MSG_SELECT_STATUS)
        await update.callback_query.message.reply_text(
            MSG_SELECT_STATUS, 
            reply_markup=build_status_inline_kb()
        )
        return TRANS_STATUS
    return TRANS_TO


async def trans_status_cb(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    if query.data.startswith(CB_STATUS_PREFIX):
        status = query.data[len(CB_STATUS_PREFIX):]
        context.user_data["status"] = status
        await query.edit_message_text(MSG_ADD_INFO_QUESTION)
        await update.callback_query.message.reply_text(
            MSG_ADD_INFO_DETAILS,
            reply_markup=build_info_inline_kb()
        )
        return TRANS_INFO
    return TRANS_STATUS


async def trans_info_cb(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith(CB_INFO_PREFIX):
        info_choice = query.data[len(CB_INFO_PREFIX):]
        
        if info_choice == BTN_NONE:
            context.user_data["info"] = ""
            return await finalize_transaction(update, context)
        else:  # BTN_YES
            await query.edit_message_text(MSG_ENTER_INFO)
            return TRANS_INFO
    return TRANS_INFO


async def trans_info_text(update: Update, context: CallbackContext) -> int:
    info = update.message.text.strip()
    context.user_data["info"] = info
    return await finalize_transaction(update, context)


async def finalize_transaction(update, context):
    today = datetime.now().strftime("%Y-%m-%d")
    context.user_data["date"] = today
    
    # Generate description based on transaction type
    trans_type = context.user_data["type"]
    amount_sent = context.user_data["amount_sent"]
    currency_sent = context.user_data["currency_sent"]
    
    if trans_type in SIMPLE_TRANSACTION_TYPES:
        description = DESC_TEMPLATE_SIMPLE.format(
            type=trans_type.capitalize(), 
            amount=amount_sent, 
            currency=currency_sent
        )
    else:
        description = DESC_TEMPLATE_COMPLEX.format(type=trans_type.capitalize())
    
    context.user_data["description"] = description

    data = load_data()
    trans = {k: context.user_data[k] for k in ["date", "type", "amount_sent", "currency_sent", "from", "amount_received", "currency_received", "to", "status", "info", "description"]}
    data["transactions"].append(trans)

    # Update balances
    await update_balances(data, trans)
    save_data(data)

    # Format response message using config templates
    if trans_type in SIMPLE_TRANSACTION_TYPES:
        response_msg = MSG_TRANSACTION_ADDED_SIMPLE.format(
            type=trans_type.capitalize(),
            date=today,
            amount=trans['amount_sent'],
            currency=trans['currency_sent'],
            account=trans['from'],
            info=trans['info'] if trans['info'] else 'None'
        )
    else:
        response_msg = MSG_TRANSACTION_ADDED_FULL.format(
            date=today,
            description=trans['description'],
            amount_sent=trans['amount_sent'],
            currency_sent=trans['currency_sent'],
            from_account=trans['from'],
            amount_received=trans['amount_received'],
            currency_received=trans['currency_received'],
            to_account=trans['to'],
            status=trans['status'],
            info=trans['info']
        )

    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.message.reply_text(response_msg, reply_markup=get_main_keyboard())
    else:
        await update.message.reply_text(response_msg, reply_markup=get_main_keyboard())
    
    return ConversationHandler.END


async def update_balances(data, trans):
    status = trans["status"]
    from_acc = trans["from"]
    to_acc = trans["to"]
    sent_curr = trans["currency_sent"]
    recv_curr = trans["currency_received"]
    sent_amt = trans["amount_sent"]
    recv_amt = trans["amount_received"]
    trans_type = trans["type"]

    if from_acc not in data["balances"]:
        data["balances"][from_acc] = {"settled": {}, "pending": {}}
    if to_acc and to_acc not in data["balances"]:
        data["balances"][to_acc] = {"settled": {}, "pending": {}}

    if status == "closed":
        # Subtract sent from from_acc settled
        data["balances"][from_acc]["settled"][sent_curr] = data["balances"][from_acc]["settled"].get(sent_curr, 0) - sent_amt
        # Add received to to_acc settled (if there's a destination account)
        if to_acc and recv_amt > 0:
            data["balances"][to_acc]["settled"][recv_curr] = data["balances"][to_acc]["settled"].get(recv_curr, 0) + recv_amt
    else:
        # Pending
        data["balances"][from_acc]["pending"][sent_curr] = data["balances"][from_acc]["pending"].get(sent_curr, 0) - sent_amt
        if to_acc and recv_amt > 0:
            data["balances"][to_acc]["pending"][recv_curr] = data["balances"][to_acc]["pending"].get(recv_curr, 0) + recv_amt

    # Update spending categories using config
    if trans_type in SPENDING_CATEGORIES:
        cat = data["spending_categories"].get(trans_type, {"transactions": [], "total": {}})
        cat["transactions"].append(trans)
        cat["total"][sent_curr] = cat["total"].get(sent_curr, 0) + sent_amt
        data["spending_categories"][trans_type] = cat


# List transactions
async def list_transactions(update: Update, context: CallbackContext) -> None:
    data = load_data()
    if not data.get("transactions"):
        await update.message.reply_text(
            MSG_NO_TRANSACTIONS, reply_markup=get_main_keyboard()
        )
        return
    items = data["transactions"][-TRANSACTION_LIST_LIMIT:][::-1]
    lines = [TABLE_HEADER, TABLE_SEPARATOR]
    for t in items:
        lines.append(
            f"| {t.get('date', '?')} | {t.get('type', '?')} | {t.get('amount_sent', 0)} | {t.get('currency_sent', '?')} | {t.get('from', '?')} | {t.get('amount_received', 0)} | {t.get('currency_received', '?')} | {t.get('to', '?')} | {t.get('status', '?')} | {t.get('info', '?')} |"
        )
    text = REPORT_HEADER_TRANSACTIONS + "\n" + "\n".join(lines)
    await update.message.reply_text(text, reply_markup=get_main_keyboard())


# Generate Report
async def generate_report(update: Update, context: CallbackContext) -> None:
    data = load_data()
    transactions = data.get("transactions", [])

    # Transactions Log using config header
    log = f"{REPORT_HEADER_LOG}\n\n{TABLE_HEADER_FULL}\n"
    for t in transactions:
        log += f"| {t['date']} | {t['type']} | {t['amount_sent']} | {t['currency_sent']} | {t['from']} | {t['amount_received']} | {t['currency_received']} | {t['to']} | {t['status']} | {t['info']} |\n"

    # Accounts using config header
    accounts_str = f"\n---\n{REPORT_HEADER_ACCOUNTS}\n"
    for acc in data.get("accounts", []):
        accounts_str += f"## {acc}\n"
        acc_trans = [t for t in transactions if t['from'] == acc or t['to'] == acc]
        for t in acc_trans:
            direction = "Sent" if t['from'] == acc else "Received"
            opp_acc = t['to'] if t['from'] == acc else t['from']
            accounts_str += f"- {t['date']} | {t['type']} | {direction} {t['amount_sent']} {t['currency_sent']} → {opp_acc} | {t['status']}  \n"
        
        settled_balances = data["balances"].get(acc, {"settled": {}}).get("settled", {})
        pending_balances = data["balances"].get(acc, {"pending": {}}).get("pending", {})
        
        settled = ", ".join([f"{curr}: {amt}" for curr, amt in settled_balances.items() if amt != 0])
        pending = ", ".join([f"{curr}: {amt}" for curr, amt in pending_balances.items() if amt != 0])
        
        accounts_str += f"**Balance:**  \n- {REPORT_BALANCE_SETTLED}: {settled or 'None'}  \n- {REPORT_BALANCE_PENDING}: {pending or 'None'}\n---\n"

    # Spending using config header
    spending = f"\n{REPORT_HEADER_SPENDING}\n"
    for cat_name, cat in data.get("spending_categories", {}).items():
        if cat_name in SPENDING_CATEGORIES:  # Only show configured spending categories
            spending += f"## {cat_name.capitalize()}\n"
            for t in cat.get("transactions", []):
                spending += f"{t['date']} | {t['amount_sent']} {t['currency_sent']} | {t['info']}\n"
            totals = " ".join([f"{curr}: {amt}" for curr, amt in cat.get("total", {}).items()])
            spending += f"Total | {totals}\n"

    full_report = log + accounts_str + spending
    await update.message.reply_text(full_report, reply_markup=get_main_keyboard())


async def send_alive(context: CallbackContext) -> None:
    """Send a periodic heartbeat message to confirm the bot is running."""
    logger.info("Bot heartbeat - I'm alive!")


async def cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text(
        MSG_CANCELLED, reply_markup=get_main_keyboard()
    )
    return ConversationHandler.END


async def on_timeout(update: Update, context: CallbackContext) -> int:
    chat = update.effective_chat
    if chat:
        await context.bot.send_message(
            chat_id=chat.id,
            text=MSG_SESSION_TIMEOUT,
            reply_markup=get_main_keyboard(),
        )
    return ConversationHandler.END



async def generate_image_report(update: Update, context: CallbackContext) -> None:
    data = load_data()
    transactions = data.get("transactions", [])

    # Reuse the same report generation logic as `generate_report`
    log = f"{REPORT_HEADER_LOG}\n\n{TABLE_HEADER_FULL}\n"
    for t in transactions:
        log += f"| {t['date']} | {t['type']} | {t['amount_sent']} | {t['currency_sent']} | {t['from']} | {t['amount_received']} | {t['currency_received']} | {t['to']} | {t['status']} | {t['info']} |\n"

    accounts_str = f"\n---\n{REPORT_HEADER_ACCOUNTS}\n"
    for acc in data.get("accounts", []):
        accounts_str += f"## {acc}\n"
        acc_trans = [t for t in transactions if t['from'] == acc or t['to'] == acc]
        for t in acc_trans:
            direction = "Sent" if t['from'] == acc else "Received"
            opp_acc = t['to'] if t['from'] == acc else t['from']
            accounts_str += f"- {t['date']} | {t['type']} | {direction} {t['amount_sent']} {t['currency_sent']} → {opp_acc} | {t['status']}  \n"
        
        settled_balances = data["balances"].get(acc, {"settled": {}}).get("settled", {})
        pending_balances = data["balances"].get(acc, {"pending": {}}).get("pending", {})
        
        settled = ", ".join([f"{curr}: {amt}" for curr, amt in settled_balances.items() if amt != 0])
        pending = ", ".join([f"{curr}: {amt}" for curr, amt in pending_balances.items() if amt != 0])
        
        accounts_str += f"**Balance:** \n- {REPORT_BALANCE_SETTLED}: {settled or 'None'}  \n- {REPORT_BALANCE_PENDING}: {pending or 'None'}\n---\n"

    spending = f"\n{REPORT_HEADER_SPENDING}\n"
    for cat_name, cat in data.get("spending_categories", {}).items():
        if cat_name in SPENDING_CATEGORIES:
            spending += f"## {cat_name.capitalize()}\n"
            for t in cat.get("transactions", []):
                spending += f"{t['date']} | {t['amount_sent']} {t['currency_sent']} | {t['info']}\n"
            totals = " ".join([f"{curr}: {amt}" for curr, amt in cat.get("total", {}).items()])
            spending += f"Total | {totals}\n"

    full_report = log + accounts_str + spending

    # Convert Markdown to HTML with a basic stylesheet for readability
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Finance Report</title>
        <style>
            body {{ font-family: monospace; font-size: 14px; white-space: pre; }}
            pre {{ margin: 0; }}
            h1, h2 {{ margin-top: 20px; }}
            table {{ border-collapse: collapse; }}
            th, td {{ border: 1px solid black; padding: 5px; }}
        </style>
    </head>
    <body>
        <pre>{full_report}</pre>
    </body>
    </html>
    """
    
    # Render HTML to image
    image_path = "report.png"
    try:
        HTML(string=html_content).write_png(image_path)
        await update.message.reply_photo(
            photo=open(image_path, 'rb'),
            reply_markup=get_main_keyboard(),
            caption="Here is your report as an image."
        )
    except Exception as e:
        logger.error(f"Error generating image report: {e}")
        await update.message.reply_text(
            "Sorry, there was an error generating the image report. Please try again later.",
            reply_markup=get_main_keyboard()
        )
    finally:
        # Clean up the generated file
        if os.path.exists(image_path):
            os.remove(image_path)




def main():
    data = load_data()
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))

    # Use config button labels for message handlers
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_LIST_TRANSACTIONS}$"), list_transactions))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_GENERATE_REPORT}$"), generate_report))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_GENERATE_IMAGE_REPORT}$"), generate_image_report))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_CANCEL}$"), cancel))

    # Delete all data conversation handler
    delete_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f"^{BTN_DELETE_ALL_DATA}$"), delete_all_data)],
        states={
            CONFIRM_DELETE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_delete)
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, on_timeout)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(filters.Regex(f"^{BTN_CANCEL}$"), cancel),
        ],
        conversation_timeout=CONVERSATION_TIMEOUT,
        per_message=False,
    )
    app.add_handler(delete_conv)

    trans_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f"^{BTN_ADD_TRANSACTION}$"), start_transaction)],
        states={
            TRANS_TYPE: [
                CallbackQueryHandler(trans_type_cb, pattern=f"^{CB_TYPE_PREFIX}")
            ],
            TRANS_AMOUNT_SENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, trans_amount_sent)
            ],
            TRANS_CURRENCY_SENT: [
                CallbackQueryHandler(trans_currency_sent_cb, pattern=f"^{CB_CURRENCY_SENT_PREFIX}")
            ],
            TRANS_FROM: [
                CallbackQueryHandler(trans_from_cb, pattern=f"^{CB_FROM_PREFIX}")
            ],
            TRANS_AMOUNT_RECEIVED: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, trans_amount_received)
            ],
            TRANS_CURRENCY_RECEIVED: [
                CallbackQueryHandler(trans_currency_received_cb, pattern=f"^{CB_CURRENCY_RECEIVED_PREFIX}")
            ],
            TRANS_TO: [
                CallbackQueryHandler(trans_to_cb, pattern=f"^{CB_TO_PREFIX}")
            ],
            TRANS_STATUS: [
                CallbackQueryHandler(trans_status_cb, pattern=f"^{CB_STATUS_PREFIX}")
            ],
            TRANS_INFO: [
                CallbackQueryHandler(trans_info_cb, pattern=f"^{CB_INFO_PREFIX}"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, trans_info_text)
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, on_timeout)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(filters.Regex(f"^{BTN_CANCEL}$"), cancel),
        ],
        conversation_timeout=CONVERSATION_TIMEOUT,
        per_message=False,
    )
    app.add_handler(trans_conv)

    manage_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f"^{BTN_MANAGE_ACCOUNTS}$"), manage_accounts)],
        states={
            MANAGE_ACCOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, modify_accounts)
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, on_timeout)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(filters.Regex(f"^{BTN_CANCEL}$"), cancel),
        ],
        conversation_timeout=CONVERSATION_TIMEOUT,
        per_message=False,
    )
    app.add_handler(manage_conv)

    # Only add job queue if it's available
    try:
        if app.job_queue:
            app.job_queue.run_repeating(
                send_alive,
                interval=timedelta(hours=HEARTBEAT_INTERVAL_HOURS).total_seconds(),
                first=0,
                name="heartbeat",
            )
    except Exception as e:
        logger.warning(f"JobQueue not available: {e}. Bot will run without heartbeat.")

    logger.info("Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()