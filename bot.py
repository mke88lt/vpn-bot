import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (Application, CommandHandler, MessageHandler,
                           CallbackQueryHandler, ContextTypes, filters, ConversationHandler)
from config import BOT_TOKEN, ADMIN_IDS, PLANS, CARD_NUMBER, CARD_OWNER
from database import *

WAITING_RECEIPT = 1
WAITING_CONFIG = 2
WAITING_BROADCAST = 3

def format_plan(key, v):
    volume = "♾ نامحدود" if v["volume_gb"] == 0 else f"📦 {v['volume_gb']} گیگ"
    return f"{v['name']} | {volume} | {v['price']:,} تومان"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user.id, user.username, user.full_name)
    kb = [
        [InlineKeyboardButton("🛒 خرید سرویس", callback_data="buy")],
        [InlineKeyboardButton("📋 اشتراک من", callback_data="my_sub")],
        [InlineKeyboardButton("📞 پشتیبانی", callback_data="support")],
    ]
    if user.id in ADMIN_IDS:
        kb.append([InlineKeyboardButton("⚙️ پنل ادمین", callback_data="admin")])
    await update.message.reply_text(
        f"👋 سلام {user.first_name}!\nبه ربات VPN خوش اومدی.",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "buy":
        kb = [[InlineKeyboardButton(format_plan(k, v), callback_data=f"plan_{k}")]
              for k, v in PLANS.items()]
        kb.append([InlineKeyboardButton("🔙 برگشت", callback_data="back_main")])
        await query.edit_message_text("📦 پلن مورد نظرت رو انتخاب کن:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("plan_"):
        plan_key = data[5:]
        plan = PLANS[plan_key]
        context.user_data["selected_plan"] = plan_key
        order_id = create_order(user_id, plan_key, plan["price"])
        context.user_data["order_id"] = order_id
        volume_text = "نامحدود" if plan["volume_gb"] == 0 else f"{plan['volume_gb']} گیگابایت"
        text = (f"✅ پلن انتخابی: {plan['name']}\n"
                f"📦 حجم: {volume_text}\n"
                f"📅 مدت: {plan['days']} روز\n"
                f"💰 مبلغ: {plan['price']:,} تومان\n\n"
                f"💳 لطفاً مبلغ رو به کارت زیر واریز کن:\n\n"
                f"🏦 شماره کارت: {CARD_NUMBER}\n"
                f"👤 به نام: {CARD_OWNER}\n\n"
                f"بعد از پرداخت، تصویر رسید رو بفرست.")
        await query.edit_message_text(text)
        return WAITING_RECEIPT

    elif data == "my_sub":
        sub = get_user_subscription(user_id)
        if sub:
            from datetime import datetime
            volume_text = "♾ نامحدود" if sub[6] == 0 else f"{sub[6]} گیگابایت"
            end_date = datetime.fromisoformat(sub[5])
            now = datetime.now()
            days_left = (end_date - now).days
            if days_left > 0:
                status = f"✅ فعال - {days_left} روز مانده"
            elif days_left == 0:
                status = "⚠️ امروز منقضی میشه!"
            else:
                status = "❌ منقضی شده"
            text = (f"📋 اشتراک شما:\n\n"
                    f"وضعیت: {status}\n"
                    f"📅 انقضا: {sub[5][:10]}\n\n"
                    f"🔑 کانفیگ:\n{sub[3]}")
        else:
            text = "❌ اشتراک فعالی نداری.\nبرای خرید از منو استفاده کن."
        await query.edit_message_text(text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 برگشت", callback_data="back_main")]]))

    elif data == "support":
        await query.edit_message_text("📞 برای پشتیبانی به @darmundeh پیام بده.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 برگشت", callback_data="back_main")]]))

    elif data == "back_main":
        kb = [
            [InlineKeyboardButton("🛒 خرید سرویس", callback_data="buy")],
            [InlineKeyboardButton("📋 اشتراک من", callback_data="my_sub")],
            [InlineKeyboardButton("📞 پشتیبانی", callback_data="support")],
        ]
        if user_id in ADMIN_IDS:
            kb.append([InlineKeyboardButton("⚙️ پنل ادمین", callback_data="admin")])
        await query.edit_message_text("منوی اصلی:", reply_markup=InlineKeyboardMarkup(kb))

    elif data == "admin" and user_id in ADMIN_IDS:
        await show_admin_panel(query)

    elif data == "admin_orders" and user_id in ADMIN_IDS:
        orders = get_pending_orders()
        if not orders:
            await query.edit_message_text("✅ سفارش در انتظاری نداری.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 برگشت", callback_data="admin")]]))
        else:
            await query.edit_message_text(f"📦 {len(orders)} سفارش در انتظار داری. در حال ارسال...")
            for order in orders:
                oid, uid, plan, amount, status, receipt, created = order
                p = PLANS.get(plan, {})
                volume_text = "نامحدود" if p.get("volume_gb", 0) == 0 else f"{p.get('volume_gb')} گیگ"
                kb = [[InlineKeyboardButton("✅ تایید", callback_data=f"approve_{oid}"),
                       InlineKeyboardButton("❌ رد", callback_data=f"reject_{oid}")]]
                await context.bot.send_photo(
                    user_id, photo=receipt,
                    caption=(f"🧾 سفارش #{oid}\n👤 یوزر: {uid}\n"
                             f"📦 پلن: {p.get('name','')}\n💾 حجم: {volume_text}\n"
                             f"💰 مبلغ: {amount:,} تومان"),
                    reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("approve_") and user_id in ADMIN_IDS:
        order_id = int(data[8:])
        result = approve_order(order_id)
        if result:
            target_user, config_text, plan_key = result
            plan = PLANS.get(plan_key, {})
            volume_text = "نامحدود" if plan.get("volume_gb", 0) == 0 else f"{plan.get('volume_gb')} گیگابایت"
            await context.bot.send_message(target_user,
                f"✅ پرداخت تایید شد!\n\n📦 پلن: {plan.get('name','')}\n"
                f"💾 حجم: {volume_text}\n📅 مدت: {plan.get('days',0)} روز\n\n"
                f"🔑 کانفیگ VPN شما:\n{config_text}")
            await query.edit_message_caption("✅ تایید شد و کانفیگ ارسال شد.")
        else:
            await query.edit_message_caption("⚠️ کانفیگ آزاد پیدا نشد! لطفاً کانفیگ اضافه کن.")

    elif data.startswith("reject_") and user_id in ADMIN_IDS:
        order_id = int(data[7:])
        target_user = reject_order(order_id)
        if target_user:
            await context.bot.send_message(target_user, "❌ پرداخت شما تایید نشد. لطفاً با پشتیبانی تماس بگیر.")
        await query.edit_message_caption("❌ سفارش رد شد.")

    elif data == "admin_users" and user_id in ADMIN_IDS:
        users = get_all_users()
        text = f"👥 تعداد کاربران: {len(users)}\n\n"
        for u in users[:20]:
            text += f"• {u[2]} (@{u[1]}) - {u[3][:10]}\n"
        await query.edit_message_text(text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 برگشت", callback_data="admin")]]))

    elif data == "admin_add_config" and user_id in ADMIN_IDS:
        kb = [[InlineKeyboardButton(format_plan(k, v), callback_data=f"cfgplan_{k}")] for k, v in PLANS.items()]
        await query.edit_message_text("برای کدوم پلن کانفیگ اضافه می‌کنی؟", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("cfgplan_") and user_id in ADMIN_IDS:
        plan_key = data[8:]
        context.user_data["adding_config_plan"] = plan_key
        await query.edit_message_text(f"کانفیگ پلن {PLANS[plan_key]['name']} رو بفرست:")
        return WAITING_CONFIG

    elif data == "admin_stats" and user_id in ADMIN_IDS:
        total_users, active_subs, total_sales, total_revenue = get_stats()
        text = (f"📊 آمار ربات:\n\n👥 کل کاربران: {total_users}\n"
                f"✅ اشتراک فعال: {active_subs}\n🛒 فروش کل: {total_sales}\n"
                f"💰 درآمد کل: {total_revenue:,} تومان")
        await query.edit_message_text(text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 برگشت", callback_data="admin")]]))

    elif data == "admin_broadcast" and user_id in ADMIN_IDS:
        await query.edit_message_text("متن پیام همگانی رو بفرست:")
        return WAITING_BROADCAST

async def show_admin_panel(query):
    kb = [
        [InlineKeyboardButton("📦 سفارش‌های در انتظار", callback_data="admin_orders")],
        [InlineKeyboardButton("👥 مدیریت کاربران", callback_data="admin_users")],
        [InlineKeyboardButton("➕ اضافه کردن کانفیگ", callback_data="admin_add_config")],
        [InlineKeyboardButton("📊 آمار", callback_data="admin_stats")],
        [InlineKeyboardButton("📣 پیام همگانی", callback_data="admin_broadcast")],
    ]
    await query.edit_message_text("⚙️ پنل ادمین:", reply_markup=InlineKeyboardMarkup(kb))

async def receive_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("لطفاً تصویر رسید رو بفرست.")
        return WAITING_RECEIPT
    file_id = update.message.photo[-1].file_id
    order_id = context.user_data.get("order_id")
    if order_id:
        update_order_receipt(order_id, file_id)
        plan_key = context.user_data.get("selected_plan")
        plan = PLANS.get(plan_key, {})
        volume_text = "نامحدود" if plan.get("volume_gb", 0) == 0 else f"{plan.get('volume_gb')} گیگ"
        kb = [[InlineKeyboardButton("✅ تایید", callback_data=f"approve_{order_id}"),
               InlineKeyboardButton("❌ رد", callback_data=f"reject_{order_id}")]]
        for admin_id in ADMIN_IDS:
            await context.bot.send_photo(admin_id, photo=file_id,
                caption=(f"🧾 سفارش جدید #{order_id}\n👤 یوزر: {update.effective_user.id}\n"
                         f"📦 پلن: {plan.get('name','')}\n💾 حجم: {volume_text}\n"
                         f"💰 {plan.get('price',0):,} تومان"),
                reply_markup=InlineKeyboardMarkup(kb))
        await update.message.reply_text("✅ رسید دریافت شد! بعد از بررسی، کانفیگت ارسال میشه.")
    return ConversationHandler.END

async def receive_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return ConversationHandler.END
    config_text = update.message.text
    plan = context.user_data.get("adding_config_plan")
    if config_text and plan:
        add_config(config_text, plan)
        await update.message.reply_text(f"✅ کانفیگ برای پلن {PLANS[plan]['name']} اضافه شد.")
    return ConversationHandler.END

async def receive_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return ConversationHandler.END
    text = update.message.text
    users = get_all_users()
    success = 0
    for u in users:
        try:
            await context.bot.send_message(u[0], text)
            success += 1
        except:
            pass
    await update.message.reply_text(f"✅ پیام به {success} نفر ارسال شد.")
    return ConversationHandler.END

def main():
    import os
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler)],
        states={
            WAITING_RECEIPT: [MessageHandler(filters.PHOTO, receive_receipt)],
            WAITING_CONFIG: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_config)],
            WAITING_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_broadcast)],
        },
        fallbacks=[CommandHandler("start", start)],
        per_message=False,
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)
    webhook_url = os.environ.get("WEBHOOK_URL")
    if webhook_url:
        print("ربات با Webhook روشن شد...")
        port = int(os.environ.get("PORT", 8443))
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            webhook_url=webhook_url,
            drop_pending_updates=True,
        )
    else:
        print("ربات با Polling روشن شد...")
        app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
