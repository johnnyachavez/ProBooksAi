"""
ProBooks+ai Telegram Bot
=========================
Send receipts, invoices, or commands from your phone — they land in the
desktop app's intake DB and are POSTed to the local FastAPI server.

Commands
--------
/start          Welcome + help
/help           List all commands
/pl             Profit & Loss (current year to date)
/balance        Balance sheet as of today
/ar             AR aging summary
/ap             AP aging summary
/invoices       List recent open invoices
/bills          List recent open bills

Attachments (photo / document)
--------------------------------
Send any photo or PDF → Claude extracts it → bot replies with extracted
fields and prompts "Route to Invoice?" or "Enter as Bill?"

Environment variables (see .env.example)
-----------------------------------------
TELEGRAM_BOT_TOKEN  — BotFather token (required)
API_BASE_URL        — ProBooks+ai API URL (default http://127.0.0.1:8000)
API_SECRET_KEY      — Bearer token matching the API server
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lazy import guard — python-telegram-bot is optional
# ---------------------------------------------------------------------------

def _require_telegram():
    try:
        import telegram  # noqa: F401
        return True
    except ImportError:
        raise ImportError(
            "python-telegram-bot is required for the Telegram bot. "
            "Install with: pip install 'python-telegram-bot>=20.0'"
        )


# ---------------------------------------------------------------------------
# API client helpers
# ---------------------------------------------------------------------------

def _api_base() -> str:
    return os.environ.get("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def _headers() -> dict:
    key = os.environ.get("API_SECRET_KEY", "").strip()
    return {"Authorization": f"Bearer {key}"} if key else {}


async def _api_get(path: str, params: Optional[dict] = None) -> dict:
    """Async GET against the local ProBooks+ai API."""
    import httpx
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{_api_base()}{path}", params=params, headers=_headers())
        r.raise_for_status()
        return r.json()


async def _api_post(path: str, json: Optional[dict] = None) -> dict:
    """Async POST against the local ProBooks+ai API."""
    import httpx
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{_api_base()}{path}", json=json, headers=_headers())
        r.raise_for_status()
        return r.json()


async def _api_upload(path: str, file_bytes: bytes, filename: str, mime: str) -> dict:
    """POST a file to /intake/document."""
    import httpx
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            f"{_api_base()}{path}",
            files={"file": (filename, file_bytes, mime)},
            headers=_headers(),
        )
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt_currency(val) -> str:
    try:
        return f"${float(val):,.2f}"
    except (TypeError, ValueError):
        return str(val or "—")


def _fmt_extraction(data: dict) -> str:
    lines = ["*AI Extraction Result*"]
    for label, key in [
        ("Vendor", "vendor"), ("Type", "doc_type"), ("Invoice #", "invoice_number"),
        ("Date", "doc_date"), ("Due", "due_date"),
        ("Subtotal", "subtotal"), ("Tax", "tax"), ("Total", "total"),
    ]:
        val = data.get(key)
        if val is not None and val != "":
            if key in ("subtotal", "tax", "total"):
                val = _fmt_currency(val)
            lines.append(f"• {label}: {val}")
    conf = data.get("confidence", 0)
    lines.append(f"• Confidence: {int(conf * 100)}%")
    if data.get("error"):
        lines.append(f"⚠️ Error: {data['error']}")
    return "\n".join(lines)


def _fmt_pl(data: dict) -> str:
    lines = ["*Profit & Loss*"]
    for k, v in data.items():
        if isinstance(v, (int, float)):
            lines.append(f"• {k}: {_fmt_currency(v)}")
        elif isinstance(v, dict):
            lines.append(f"\n_{k}_")
            for sk, sv in v.items():
                if isinstance(sv, (int, float)):
                    lines.append(f"  • {sk}: {_fmt_currency(sv)}")
    return "\n".join(lines)


def _fmt_balance(data: dict) -> str:
    lines = ["*Balance Sheet*"]
    for section, items in data.items():
        lines.append(f"\n_{section}_")
        if isinstance(items, dict):
            for k, v in items.items():
                lines.append(f"  • {k}: {_fmt_currency(v)}")
        elif isinstance(items, (int, float)):
            lines.append(f"  {_fmt_currency(items)}")
    return "\n".join(lines)


def _fmt_aging(rows: list, label: str) -> str:
    if not rows:
        return f"*{label} Aging*\nNo open items."
    lines = [f"*{label} Aging*"]
    for row in rows:
        name = row.get("name") or row.get("vendor_name") or row.get("customer_name") or "?"
        total = _fmt_currency(row.get("total") or row.get("balance") or 0)
        lines.append(f"• {name}: {total}")
    return "\n".join(lines)


def _fmt_invoices(rows: list) -> str:
    if not rows:
        return "*Open Invoices*\nNone."
    lines = ["*Recent Invoices*"]
    for r in rows[:10]:
        num = r.get("invoice_number") or r.get("id") or "?"
        cust = r.get("customer_name") or r.get("name") or "?"
        total = _fmt_currency(r.get("total") or 0)
        lines.append(f"• #{num} — {cust}: {total}")
    return "\n".join(lines)


def _fmt_bills(rows: list) -> str:
    if not rows:
        return "*Bills*\nNone."
    lines = ["*Recent Bills*"]
    for r in rows[:10]:
        vendor = r.get("vendor_name") or r.get("name") or "?"
        total = _fmt_currency(r.get("total") or 0)
        due = r.get("due_date") or ""
        lines.append(f"• {vendor}: {total}" + (f" (due {due})" if due else ""))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Bot handlers
# ---------------------------------------------------------------------------

async def _cmd_start(update, context) -> None:
    await update.message.reply_text(
        "👋 *ProBooks+ai Bot*\n\n"
        "Send me a photo or PDF of a receipt/invoice — I'll extract it with AI "
        "and ask if you want to route it to an invoice or bill.\n\n"
        "Commands: /pl /balance /ar /ap /invoices /bills /help",
        parse_mode="Markdown",
    )


async def _cmd_help(update, context) -> None:
    await update.message.reply_text(
        "*Commands*\n"
        "/pl — Profit & Loss (year to date)\n"
        "/balance — Balance sheet (today)\n"
        "/ar — AR aging\n"
        "/ap — AP aging\n"
        "/invoices — Recent invoices\n"
        "/bills — Recent bills\n\n"
        "Send a photo or PDF → AI extraction + route to Invoice or Bill.",
        parse_mode="Markdown",
    )


async def _cmd_pl(update, context) -> None:
    try:
        data = await _api_get("/reports/pl")
        await update.message.reply_text(_fmt_pl(data), parse_mode="Markdown")
    except Exception as exc:
        await update.message.reply_text(f"⚠️ Could not fetch P&L: {exc}")


async def _cmd_balance(update, context) -> None:
    try:
        data = await _api_get("/reports/balance")
        await update.message.reply_text(_fmt_balance(data), parse_mode="Markdown")
    except Exception as exc:
        await update.message.reply_text(f"⚠️ Could not fetch balance sheet: {exc}")


async def _cmd_ar(update, context) -> None:
    try:
        data = await _api_get("/reports/aging/ar")
        rows = data if isinstance(data, list) else data.get("aging", [])
        await update.message.reply_text(_fmt_aging(rows, "AR"), parse_mode="Markdown")
    except Exception as exc:
        await update.message.reply_text(f"⚠️ Could not fetch AR aging: {exc}")


async def _cmd_ap(update, context) -> None:
    try:
        data = await _api_get("/reports/aging/ap")
        rows = data if isinstance(data, list) else data.get("aging", [])
        await update.message.reply_text(_fmt_aging(rows, "AP"), parse_mode="Markdown")
    except Exception as exc:
        await update.message.reply_text(f"⚠️ Could not fetch AP aging: {exc}")


async def _cmd_invoices(update, context) -> None:
    try:
        data = await _api_get("/invoices")
        await update.message.reply_text(
            _fmt_invoices(data.get("invoices", [])), parse_mode="Markdown"
        )
    except Exception as exc:
        await update.message.reply_text(f"⚠️ Could not fetch invoices: {exc}")


async def _cmd_bills(update, context) -> None:
    try:
        data = await _api_get("/bills")
        await update.message.reply_text(
            _fmt_bills(data.get("bills", [])), parse_mode="Markdown"
        )
    except Exception as exc:
        await update.message.reply_text(f"⚠️ Could not fetch bills: {exc}")


async def _handle_document(update, context) -> None:
    """Handle photo or file attachment — extract via AI and prompt routing."""
    msg = update.message
    await msg.reply_text("⏳ Processing document with AI…")

    try:
        if msg.photo:
            # Largest photo size
            photo = msg.photo[-1]
            tg_file = await context.bot.get_file(photo.file_id)
            filename = f"photo_{photo.file_id}.jpg"
            mime = "image/jpeg"
        elif msg.document:
            doc = msg.document
            tg_file = await context.bot.get_file(doc.file_id)
            filename = doc.file_name or f"upload_{doc.file_id}"
            mime = doc.mime_type or "application/octet-stream"
        else:
            await msg.reply_text("Please send a photo or PDF file.")
            return

        # Download file bytes
        file_bytes = await tg_file.download_as_bytearray()

        # Upload to ProBooks+ai API
        result = await _api_upload("/intake/document", bytes(file_bytes), filename, mime)

        # Reply with extraction
        reply = _fmt_extraction(result)
        doc_id = result.get("doc_id")

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        keyboard = []
        if doc_id and not result.get("error"):
            keyboard = [[
                InlineKeyboardButton(
                    "📄 Create Invoice", callback_data=f"invoice:{doc_id}"
                ),
                InlineKeyboardButton(
                    "📥 Enter as Bill", callback_data=f"bill:{doc_id}"
                ),
            ]]
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        await msg.reply_text(reply, parse_mode="Markdown", reply_markup=reply_markup)

    except Exception as exc:
        logger.exception("Document handling failed")
        await msg.reply_text(f"⚠️ Error processing document: {exc}")


async def _handle_callback(update, context) -> None:
    """Handle inline button presses (invoice / bill routing)."""
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    try:
        action, doc_id_str = data.split(":", 1)
        doc_id = int(doc_id_str)

        # Fetch the extraction from the API
        doc_data = await _api_get(f"/documents/{doc_id}")
        extraction = doc_data.get("extraction") or {}

        if action == "invoice":
            payload = {
                "customer_name": extraction.get("vendor") or "Unknown Customer",
                "invoice_number": extraction.get("invoice_number") or "",
                "invoice_date": extraction.get("doc_date") or "",
                "due_date": extraction.get("due_date") or "",
                "memo": extraction.get("notes") or "",
            }
            result = await _api_post("/invoices", json=payload)
            await query.edit_message_text(
                f"✅ Invoice created (#{payload['invoice_number'] or result.get('id')}) "
                f"for {payload['customer_name']}.",
                parse_mode="Markdown",
            )

        elif action == "bill":
            payload = {
                "vendor_name": extraction.get("vendor") or "Unknown Vendor",
                "vendor_invoice_number": extraction.get("invoice_number") or "",
                "bill_date": extraction.get("doc_date") or "",
                "due_date": extraction.get("due_date") or "",
                "total": float(extraction.get("total") or 0),
                "memo": extraction.get("notes") or "",
            }
            result = await _api_post("/bills", json=payload)
            await query.edit_message_text(
                f"✅ Bill created for {payload['vendor_name']} "
                f"({_fmt_currency(payload['total'])}).",
                parse_mode="Markdown",
            )

    except Exception as exc:
        logger.exception("Callback handling failed")
        await query.edit_message_text(f"⚠️ Error: {exc}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_bot() -> None:
    """Start the Telegram bot (blocking — runs until Ctrl+C)."""
    _require_telegram()
    from telegram.ext import (
        Application,
        CallbackQueryHandler,
        CommandHandler,
        MessageHandler,
        filters,
    )

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN environment variable is not set. "
            "Create a bot via @BotFather on Telegram and set the token."
        )

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", _cmd_start))
    app.add_handler(CommandHandler("help", _cmd_help))
    app.add_handler(CommandHandler("pl", _cmd_pl))
    app.add_handler(CommandHandler("balance", _cmd_balance))
    app.add_handler(CommandHandler("ar", _cmd_ar))
    app.add_handler(CommandHandler("ap", _cmd_ap))
    app.add_handler(CommandHandler("invoices", _cmd_invoices))
    app.add_handler(CommandHandler("bills", _cmd_bills))
    app.add_handler(
        MessageHandler(filters.PHOTO | filters.Document.ALL, _handle_document)
    )
    app.add_handler(CallbackQueryHandler(_handle_callback))

    logger.info("ProBooks+ai Telegram bot starting…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_bot()
