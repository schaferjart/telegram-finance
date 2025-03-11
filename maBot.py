import json
import logging
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, ConversationHandler
from telegram.error import TelegramError
import pytz


# Set up logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot Token
from config import TOKEN
from config import GROUP_CHAT_ID

# Data storage
DATA_FILE = "wg_data_beta.json"

def load_data():
    try:
        with open(DATA_FILE, "r") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        default_data = {"expenses": [], "chores": {}, "penalties": {}, "members": []}
        with open(DATA_FILE, "w") as file:
            json.dump(default_data, file, indent=4)
        return default_data

def save_data(data):
    with open(DATA_FILE, "w") as file:
        json.dump(data, file, indent=4)

# States for conversation handler
EXPENSE_AMOUNT, EXPENSE_PAYER, EXPENSE_SPLIT, EXPENSE_CONFIRM = range(4)
CHORE_USER, CHORE_MINUTES = range(2)
MANAGE_MEMBER = range(1)

# Dynamic Keyboards
def get_main_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("Add Expense"), KeyboardButton("Add Chore")],
        [KeyboardButton("Standings"), KeyboardButton("Check Beer Owed")],
        [KeyboardButton("Manage Members"), KeyboardButton("Set Weekly Report")]
    ], resize_keyboard=True)

def get_member_keyboard(data):
    members = data.get("members", [])
    if not members:
        return None
    # Display the members as they are stored (without lowercasing them)
    buttons = [[KeyboardButton(member)] for member in members]
    buttons.append([KeyboardButton("Done")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

async def start(update: Update, context: CallbackContext) -> None:
    data = load_data()
    await update.message.reply_text("WG Bot is active! Use the buttons below:", reply_markup=get_main_keyboard())

# Manage Members
async def manage_members(update: Update, context: CallbackContext) -> int:
    data = load_data()
    
    # Display current members list
    if data["members"]:
        members_list = ", ".join(data["members"])
        await update.message.reply_text(f"Current members: {members_list}\n\nEnter the name of the member to add or remove:", reply_markup=ReplyKeyboardRemove())
    else:
        await update.message.reply_text("No members yet. Enter the name of a member to add:", reply_markup=ReplyKeyboardRemove())
    
    return MANAGE_MEMBER

async def modify_members(update: Update, context: CallbackContext) -> int:
    data = load_data()
    member = update.message.text.strip().lower()

    if member in data["members"]:
        data["members"].remove(member)
        response = f"Removed {member} from the household."
    else:
        data["members"].append(member)
        response = f"Added {member} to the household."

    save_data(data)
    await update.message.reply_text(response, reply_markup=get_main_keyboard())
    return ConversationHandler.END

# Expense flow
async def start_expense(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("Enter the amount:", reply_markup=ReplyKeyboardRemove())
    return EXPENSE_AMOUNT

async def expense_amount(update: Update, context: CallbackContext) -> int:
    try:
        context.user_data['amount'] = round(float(update.message.text), 2)
        data = load_data()
        keyboard = get_member_keyboard(data)
        if keyboard:
            await update.message.reply_text("Who paid?", reply_markup=keyboard)
        else:
            await update.message.reply_text("No members found. Please add members first.", reply_markup=get_main_keyboard())
            return ConversationHandler.END
        return EXPENSE_PAYER
    except ValueError:
        await update.message.reply_text("Invalid amount. Try again.")
        return EXPENSE_AMOUNT

async def expense_payer(update: Update, context: CallbackContext) -> int:
    context.user_data['payer'] = update.message.text.strip()
    context.user_data['split_with'] = []
    data = load_data()
    keyboard = get_member_keyboard(data)
    if keyboard:
        await update.message.reply_text("Who should split the expense? Select names and press 'Done' when finished:", reply_markup=keyboard)
    else:
        await update.message.reply_text("No members found. Please add members first.", reply_markup=get_main_keyboard())
        return ConversationHandler.END
    return EXPENSE_SPLIT

async def expense_split(update: Update, context: CallbackContext) -> int:
    data = load_data()
    # Get the exact text as entered by the user
    user_input = update.message.text.strip()
    
    # Handle "Done" case (case-insensitive)
    if user_input.lower() == "done":
        if not context.user_data.get('split_with', []):
            await update.message.reply_text("You must select at least one person to split with.")
            return EXPENSE_SPLIT
        else:
            amount = context.user_data['amount']
            payer = context.user_data['payer']
            split_with = context.user_data['split_with']

            data["expenses"].append({
                "amount": amount,
                "payer": payer,
                "split_with": split_with
            })
            save_data(data)

            await update.message.reply_text(f"Expense of {amount:.2f} added by {payer} shared with {', '.join(split_with)}", reply_markup=get_main_keyboard())
            return ConversationHandler.END

    # Make sure split_with exists in user_data
    if 'split_with' not in context.user_data:
        context.user_data['split_with'] = []
    
    # Check if user is in members list using the exact case as stored
    if user_input in data['members'] and user_input not in context.user_data['split_with']:
        context.user_data['split_with'].append(user_input)
        await update.message.reply_text(f"{user_input} added. Select more or press 'Done' when finished.")
    else:
        # Provide more detailed error message
        if user_input not in data['members']:
            await update.message.reply_text(f"'{user_input}' is not a valid member. Please select from the keyboard.")
        else:
            await update.message.reply_text(f"'{user_input}' has already been added to split list.")

    return EXPENSE_SPLIT

# Chore flow
async def start_chore(update: Update, context: CallbackContext) -> int:
    data = load_data()
    keyboard = get_member_keyboard(data)
    if keyboard:
        await update.message.reply_text("Who completed the chore?", reply_markup=keyboard)
    else:
        await update.message.reply_text("No members found. Please add members first.", reply_markup=get_main_keyboard())
        return ConversationHandler.END
    return CHORE_USER

async def chore_user(update: Update, context: CallbackContext) -> int:
    context.user_data['user'] = update.message.text.strip()
    await update.message.reply_text("How many minutes did it take?", reply_markup=ReplyKeyboardRemove())
    return CHORE_MINUTES

async def chore_minutes(update: Update, context: CallbackContext) -> int:
    data = load_data()
    try:
        minutes = int(update.message.text)
        points = minutes // 15
        user = context.user_data['user']
        data["chores"][user] = data["chores"].get(user, 0) + points
        save_data(data)
        await update.message.reply_text(f"{user} earned {points} points!", reply_markup=get_main_keyboard())
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Invalid input. Enter the minutes again.")
        return CHORE_MINUTES

# Show standings with balance calculation
async def standings(update: Update, context: CallbackContext) -> None:
    data = load_data()
    
    # Create a case-insensitive lookup dictionary
    member_case_map = {member.lower(): member for member in data["members"]}
    
    # Initialize balances for all members
    balances = {member: 0 for member in data["members"]}
    
    for expense in data["expenses"]:
        payer = expense["payer"]
        amount = expense["amount"]
        split_with = expense["split_with"]
        share = amount / len(split_with)
        
        # Find the correct case for the payer
        payer_key = None
        for member in data["members"]:
            if member.lower() == payer.lower():
                payer_key = member
                break
        
        if payer_key:
            balances[payer_key] = balances.get(payer_key, 0) + amount
        
        # Process each person who shares the expense
        for user in split_with:
            user_key = None
            for member in data["members"]:
                if member.lower() == user.lower():
                    user_key = member
                    break
            
            if user_key:
                balances[user_key] = balances.get(user_key, 0) - share
    
    # Create a case-insensitive lookup for chores as well
    chores_normalized = {}
    for chore_user, points in data["chores"].items():
        for member in data["members"]:
            if member.lower() == chore_user.lower():
                chores_normalized[member] = points
                break
    
    standings_text = "Chore Standings + Financial Balance:\n"
    
    # Create combined standings with all members
    all_members = set(data["members"])
    
    # Show members with chores first
    for member in sorted(all_members, key=lambda m: chores_normalized.get(m, 0), reverse=True):
        points = chores_normalized.get(member, 0)
        balance = balances.get(member, 0)
        balance_text = f"(Balance: {balance:+.2f}€)"
        standings_text += f"{member}: {points} points {balance_text}\n"
    
    if not data["members"]:
        standings_text += "No members recorded yet."
    elif not chores_normalized:
        standings_text += "No chores recorded yet."
        
    await update.message.reply_text(standings_text)

# Beer owed
async def beer_owed(update: Update, context: CallbackContext) -> None:
    data = load_data()
    leaderboard = sorted(data["chores"].items(), key=lambda x: -x[1])
    if not leaderboard:
        await update.message.reply_text("No chores recorded yet.")
        return

    leader_points = leaderboard[0][1]
    violators = []

    for user, points in leaderboard[1:]:
        if leader_points - points > 4:
            weeks_lagging = data["penalties"].get(user, 0) + 1
            data["penalties"][user] = weeks_lagging
            violators.append(f"{user} owes {weeks_lagging} beers!")

    save_data(data)
    if violators:
        await update.message.reply_text("Beer Penalties:\n" + "\n".join(violators))
    else:
        await update.message.reply_text("No penalties this week!")

# Weekly report handling
async def set_weekly_report(update: Update, context: CallbackContext) -> None:
    data = load_data()
    
    # If called from a group chat, save this chat ID for weekly reports
    if update.effective_chat.type in ["group", "supergroup"]:
        data["group_chat_id"] = update.effective_chat.id
        save_data(data)
        await update.message.reply_text("Weekly reports will be sent to this group every Monday!")
    else:
        # If we already have a group chat ID stored
        if "group_chat_id" in data:
            await update.message.reply_text(f"Weekly reports are set to be sent to a group chat. To change the group, use this command in the new group chat.")
        else:
            await update.message.reply_text("Please use this command in the group chat where you want the weekly reports to be sent.")

# Function to check penalties and send weekly report
async def check_weekly_penalties(context: CallbackContext) -> None:
    data = load_data()
    
    # Skip if no group chat is set
    if "group_chat_id" not in data:
        logger.warning("No group chat ID set for weekly reports")
        return
    
    group_id = data["group_chat_id"]
    
    # Check if we have members and chores
    if not data["members"] or not data["chores"]:
        try:
            await context.bot.send_message(
                chat_id=group_id,
                text="Weekly Report: Not enough data to calculate penalties. Make sure members are added and chores are recorded."
            )
        except TelegramError as e:
            logger.error(f"Failed to send weekly report: {e}")
        return
    
    # Create a case-insensitive lookup for chores
    chores_normalized = {}
    for chore_user, points in data["chores"].items():
        for member in data["members"]:
            if member.lower() == chore_user.lower():
                chores_normalized[member] = points
                break
    
    # Sort members by chore points
    leaderboard = sorted(
        [(member, chores_normalized.get(member, 0)) for member in data["members"]], 
        key=lambda x: -x[1]
    )
    
    if not leaderboard:
        return
    
    leader, leader_points = leaderboard[0]
    violators = []
    
    # Check for members lagging behind
    for member, points in leaderboard[1:]:
        if leader_points - points > 4:
            # Check if they've been lagging for more than a week
            last_week_violator = data.get("last_week_violators", {}).get(member.lower(), False)
            
            if last_week_violator:
                # They've been lagging for more than a week, apply penalty
                weeks_lagging = data["penalties"].get(member, 0) + 1
                data["penalties"][member] = weeks_lagging
                violators.append(f"{member} owes {weeks_lagging} beers! 🍺")
            else:
                # First week they're lagging, mark them
                if "last_week_violators" not in data:
                    data["last_week_violators"] = {}
                data["last_week_violators"][member.lower()] = True
                violators.append(f"{member} is lagging by {leader_points - points} points behind {leader}. If not improved by next week, beer penalty will apply! ⚠️")
        elif member.lower() in data.get("last_week_violators", {}):
            # They were lagging but have improved
            data["last_week_violators"].pop(member.lower(), None)
            violators.append(f"{member} has improved their standing! No beer penalty this week. 👍")
    
    save_data(data)
    
    # Prepare and send the report
    current_date = datetime.now().strftime("%Y-%m-%d")
    if violators:
        report = f"📊 Weekly Chore Report ({current_date}):\n\n"
        report += f"👑 Leader: {leader} with {leader_points} points\n\n"
        report += "Penalties:\n" + "\n".join(violators)
    else:
        report = f"📊 Weekly Chore Report ({current_date}):\n\n"
        report += f"👑 Leader: {leader} with {leader_points} points\n\n"
        report += "Everyone is keeping up with their chores! No penalties this week. 🎉"
    
    try:
        await context.bot.send_message(chat_id=group_id, text=report)
    except TelegramError as e:
        logger.error(f"Failed to send weekly report: {e}")

# Function to set up the recurring weekly job
def setup_weekly_job(application):
    # Schedule for Monday at 9:00 AM (adjust timezone as needed)
    target_time = datetime.now(pytz.timezone('Europe/Berlin'))
    target_time = target_time.replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    
    # If today is past Monday 9 AM, schedule for next Monday
    if target_time.weekday() != 0 or datetime.now(pytz.timezone('Europe/Berlin')) > target_time:
        days_until_monday = (7 - target_time.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        target_time = target_time + timedelta(days=days_until_monday)
    
    # Calculate seconds until the target time
    current_time = datetime.now(pytz.timezone('Europe/Berlin'))
    seconds_until_target = (target_time - current_time).total_seconds()
    
    # Schedule the job
    application.job_queue.run_repeating(
        check_weekly_penalties,
        interval=timedelta(days=7).total_seconds(),  # Run every 7 days
        first=seconds_until_target,
        name="weekly_penalty_check"
    )
    logger.info(f"Weekly report scheduled for {target_time.strftime('%Y-%m-%d %H:%M:%S')}")

def main():
    # Initialize data at startup
    data = load_data()
    
    # Create application
    app = Application.builder().token(TOKEN).build()
    
    # Add command handlers
    app.add_handler(CommandHandler("start", start))
    
    # Add message handlers
    app.add_handler(MessageHandler(filters.Regex("^Standings$"), standings))
    app.add_handler(MessageHandler(filters.Regex("^Check Beer Owed$"), beer_owed))
    app.add_handler(MessageHandler(filters.Regex("^Set Weekly Report$"), set_weekly_report))
    
    # Add conversation handlers
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Manage Members$"), manage_members)],
        states={
            MANAGE_MEMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, modify_members)],
        },
        fallbacks=[CommandHandler("cancel", start)]
    ))
    
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Add Expense$"), start_expense)],
        states={
            EXPENSE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, expense_amount)],
            EXPENSE_PAYER: [MessageHandler(filters.TEXT & ~filters.COMMAND, expense_payer)],
            EXPENSE_SPLIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, expense_split)],
        },
        fallbacks=[CommandHandler("cancel", start)]
    ))
    
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Add Chore$"), start_chore)],
        states={
            CHORE_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, chore_user)],
            CHORE_MINUTES: [MessageHandler(filters.TEXT & ~filters.COMMAND, chore_minutes)],
        },
        fallbacks=[CommandHandler("cancel", start)]
    ))
    
    # Start the Bot
    logger.info("Bot running...")
    app.run_polling()

if __name__ == '__main__':
    main()