"""
StudyBuddy - SSLCommerz Developer Sandbox Payment Monitor
Displays configuration, real-time transaction ledger, metrics, and monitoring tools.
"""

import sys
import os

# Path resolution
_current_dir = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.join(_current_dir, "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

import asyncio
from datetime import datetime
from app.config import settings
from app.database import init_database, get_payments_collection, get_users_collection, using_mock_db

async def run_monitor():
    await init_database()
    payments_col = get_payments_collection()
    users_col = get_users_collection()

    # Query metrics
    cursor = payments_col.find({}).sort("created_at", -1)
    if hasattr(cursor, "to_list"):
        transactions = await cursor.to_list(length=100)
    else:
        transactions = list(cursor)

    total_count = len(transactions)
    completed_count = sum(1 for t in transactions if t.get("status") == "completed")
    pending_count = sum(1 for t in transactions if t.get("status") == "pending")
    failed_count = sum(1 for t in transactions if t.get("status") in ("failed", "cancelled"))
    total_revenue = sum(float(t.get("amount", 0.0)) for t in transactions if t.get("status") == "completed")

    # Pro users count
    u_cursor = users_col.find({"plan": "pro"})
    if hasattr(u_cursor, "to_list"):
        pro_users = await u_cursor.to_list(length=100)
    else:
        pro_users = list(u_cursor)
    pro_count = len(pro_users)

    print("=" * 80)
    print("      STUDYBUDDY - SSLCOMMERZ DEVELOPER SANDBOX PAYMENT MONITOR")
    print("=" * 80)
    print(f"• Environment:        {'Local JSON Repository' if using_mock_db else 'Live MongoDB Atlas'}")
    print(f"• SSLCommerz Mode:    SANDBOX (Store ID: {settings.SSLCOMMERZ_STORE_ID})")
    print(f"• Base Pricing:       ৳{settings.PRO_BASE_PRICE_BDT:.2f} BDT / month")
    print(f"• Scholar XP Bonus:   5% Discount for users with > 250 XP (৳{settings.PRO_BASE_PRICE_BDT * 0.95:.2f} BDT)")
    print(f"• Sandbox Gateway:    https://sandbox.sslcommerz.com/gwprocess/v4/api.php")
    print(f"• Local Mock Gateway: {settings.BACKEND_BASE_URL}/api/payment/sandbox-checkout/<tran_id>")
    print("-" * 80)
    print(f"  TOTAL TRANSACTIONS: {total_count}  |  COMPLETED: {completed_count}  |  PENDING: {pending_count}  |  FAILED: {failed_count}")
    print(f"  TOTAL REVENUE:     ৳{total_revenue:.2f} BDT  |  ACTIVE PRO USERS: {pro_count}")
    print("=" * 80)
    print("")

    if not transactions:
        print("  [No payment transactions recorded yet. Initiate an upgrade from the app to test.]\n")
    else:
        print("REAL-TIME TRANSACTION LEDGER:")
        print("-" * 80)
        header = f"{'TRANSACTION ID':<26} {'CUSTOMER':<14} {'AMOUNT':<10} {'DISCOUNT':<10} {'METHOD':<14} {'STATUS':<10}"
        print(header)
        print("-" * 80)
        for t in transactions:
            tid = (t.get("transaction_id") or "")[:25]
            cust = (t.get("user_name") or t.get("user_email") or "Student")[:13]
            amt = f"৳{float(t.get('amount', 0.0)):.2f}"
            disc = f"-{t.get('discount_percent', 0.0)}%" if t.get('discount_percent', 0.0) > 0 else "0%"
            method = (t.get("payment_method") or "Sandbox")[:13]
            stat = (t.get("status") or "pending").upper()
            stat_str = f"\033[92m{stat}\033[0m" if stat == "COMPLETED" else f"\033[93m{stat}\033[0m"
            print(f"{tid:<26} {cust:<14} {amt:<10} {disc:<10} {method:<14} {stat:<10}")
        print("-" * 80)
        print("")

    print("MONITORING ACCESS CHANNELS:")
    print(" 1. Interactive Swagger UI:   http://127.0.0.1:8000/docs#/Payment%20%26%20SSLCommerz%20Sandbox")
    print(" 2. Live Transaction Check:   GET http://127.0.0.1:8000/api/payment/status/<tran_id>")
    print(" 3. Developer Simulation:     POST http://127.0.0.1:8000/api/payment/simulate-success/<tran_id>")
    print(" 4. Interactive Browser Mock: http://127.0.0.1:8000/api/payment/sandbox-checkout/<tran_id>")
    print(" 5. Database Direct View:     collection 'payments' in studybuddy_db")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(run_monitor())
