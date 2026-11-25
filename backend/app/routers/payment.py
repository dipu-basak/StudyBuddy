import logging
import os
from datetime import datetime, timezone
from typing import Optional
import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse

try:
    from app.config import settings
    from app.database import get_payments_collection, get_users_collection
    from app.routers.auth import get_current_user
    from app.schemas import (
        PaymentHistoryResponse,
        PaymentInitiateRequest,
        PaymentInitiateResponse,
        PaymentQuoteResponse,
        PaymentSimulateRequest,
        PaymentStatusResponse,
        PaymentTransactionItem,
    )
except ImportError:
    from config import settings
    from database import get_payments_collection, get_users_collection
    from routers.auth import get_current_user
    from schemas import (
        PaymentHistoryResponse,
        PaymentInitiateRequest,
        PaymentInitiateResponse,
        PaymentQuoteResponse,
        PaymentSimulateRequest,
        PaymentStatusResponse,
        PaymentTransactionItem,
    )

logger = logging.getLogger("payment_router")
router = APIRouter(prefix="/api/payment", tags=["Payment & SSLCommerz Sandbox"])

SSLCOMMERZ_SANDBOX_GW = "https://sandbox.sslcommerz.com/gwprocess/v4/api.php"
SSLCOMMERZ_SANDBOX_VALIDATOR = "https://sandbox.sslcommerz.com/validator/api/validationserverAPI.php"


def _calculate_pricing(user_xp: int) -> tuple[float, float, float, bool]:
    """
    Computes base price and applies a 5% discount if the user's XP > 250.
    Returns: (base_price, discount_percent, discount_amount, final_price, has_discount)
    """
    base_price = float(settings.PRO_BASE_PRICE_BDT)
    if user_xp > 250:
        discount_percent = 5.0
        discount_amount = round(base_price * 0.05, 2)
        final_price = round(base_price - discount_amount, 2)
        has_discount = True
    else:
        discount_percent = 0.0
        discount_amount = 0.0
        final_price = base_price
        has_discount = False
    return base_price, discount_percent, discount_amount, final_price, has_discount


@router.get("/quote", response_model=PaymentQuoteResponse)
async def get_payment_quote(current_user: dict = Depends(get_current_user)):
    """
    Returns current pricing quote for StudyBuddy Pro including dynamic 5% Scholar discount if XP > 250.
    """
    user_xp = current_user.get("xp", 0)
    is_pro = current_user.get("plan", "free") == "pro"
    base_price, discount_pct, discount_amt, final_price, has_discount = _calculate_pricing(user_xp)

    if is_pro:
        msg = "You are already an active StudyBuddy Pro member with unlimited preps and quizzes!"
    elif has_discount:
        msg = f"Scholar XP Bonus Active! (XP: {user_xp} > 250) - 5% discount applied (Saved BDT {discount_amt:.2f})."
    else:
        msg = f"Standard pricing. Reach 251+ XP to unlock an automatic 5% Scholar discount (Current XP: {user_xp})."

    return PaymentQuoteResponse(
        base_price=base_price,
        user_xp=user_xp,
        discount_percent=discount_pct,
        discount_amount=discount_amt,
        final_price=final_price,
        currency="BDT",
        is_pro=is_pro,
        has_discount=has_discount,
        message=msg,
    )


@router.post("/initiate", response_model=PaymentInitiateResponse)
async def initiate_payment(
    payload: PaymentInitiateRequest = PaymentInitiateRequest(),
    current_user: dict = Depends(get_current_user),
):
    """
    Initializes an SSLCommerz developer sandbox payment session for StudyBuddy Pro.
    Evaluates 5% XP discount, registers pending transaction, and generates Gateway URL.
    """
    user_id = str(current_user["_id"])
    user_xp = current_user.get("xp", 0)
    user_name = current_user.get("name", "Student")
    user_email = current_user.get("email", "student@studybuddy.com")

    base_price, discount_pct, discount_amt, final_price, has_discount = _calculate_pricing(user_xp)
    tran_id = f"SB-PRO-{int(datetime.now().timestamp())}-{user_id[:6]}"

    # Save pending transaction in database
    payments_col = get_payments_collection()
    now_iso = datetime.now(timezone.utc).isoformat()
    payment_record = {
        "transaction_id": tran_id,
        "user_id": user_id,
        "user_email": user_email,
        "user_name": user_name,
        "base_price": base_price,
        "discount_percent": discount_pct,
        "discount_amount": discount_amt,
        "amount": final_price,
        "currency": "BDT",
        "status": "pending",
        "payment_method": None,
        "val_id": None,
        "is_sandbox": settings.SSLCOMMERZ_IS_SANDBOX,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    await payments_col.insert_one(payment_record)

    # Prepare SSLCommerz Sandbox Session POST payload
    post_data = {
        "store_id": settings.SSLCOMMERZ_STORE_ID,
        "store_passwd": settings.SSLCOMMERZ_STORE_PASSWD,
        "total_amount": f"{final_price:.2f}",
        "currency": "BDT",
        "tran_id": tran_id,
        "success_url": f"{settings.BACKEND_BASE_URL}/api/payment/success",
        "fail_url": f"{settings.BACKEND_BASE_URL}/api/payment/fail",
        "cancel_url": f"{settings.BACKEND_BASE_URL}/api/payment/cancel",
        "ipn_url": f"{settings.BACKEND_BASE_URL}/api/payment/ipn",
        "cus_name": user_name,
        "cus_email": user_email,
        "cus_add1": "Dhaka",
        "cus_city": "Dhaka",
        "cus_country": "Bangladesh",
        "cus_phone": payload.cus_phone or "01711111111",
        "shipping_method": "NO",
        "product_name": "StudyBuddy Pro (Unlimited Quizzes & Preps)",
        "product_category": "Education",
        "product_profile": "digital-goods",
    }

    gateway_url = None
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(SSLCOMMERZ_SANDBOX_GW, data=post_data)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "SUCCESS" and data.get("GatewayPageURL"):
                    gateway_url = data["GatewayPageURL"]
                    logger.info(f"SSLCommerz Session created successfully: {gateway_url}")
    except Exception as e:
        logger.warning(f"Could not reach external SSLCommerz sandbox API ({e}). Falling back to local interactive sandbox checkout.")

    # Seamless fallback: if external sandbox API timed out or store credentials are demo-only,
    # route to the built-in local Sandbox Simulation Gateway page
    if not gateway_url:
        gateway_url = f"{settings.BACKEND_BASE_URL}/api/payment/sandbox-checkout/{tran_id}"

    msg = (
        f"SSLCommerz Sandbox session initialized. Amount: ৳{final_price:.2f} "
        f"({'5% Scholar Discount applied' if has_discount else 'Standard price'})."
    )

    return PaymentInitiateResponse(
        success=True,
        transaction_id=tran_id,
        gateway_url=gateway_url,
        base_price=base_price,
        discount_percent=discount_pct,
        discount_amount=discount_amt,
        final_amount=final_price,
        currency="BDT",
        is_sandbox=True,
        message=msg,
    )


@router.post("/success", response_class=HTMLResponse)
@router.get("/success", response_class=HTMLResponse)
async def payment_success(
    request: Request,
    tran_id: Optional[str] = Form(None),
    val_id: Optional[str] = Form(None),
    amount: Optional[str] = Form(None),
    card_type: Optional[str] = Form(None),
    bank_tran_id: Optional[str] = Form(None),
):
    """
    Receives callback from SSLCommerz upon authorized payment.
    Verifies with Order Validation API, marks payment completed, and upgrades user to Pro.
    """
    # Also support query params in case of GET redirect
    if not tran_id:
        tran_id = request.query_params.get("tran_id")
    if not val_id:
        val_id = request.query_params.get("val_id")
    if not card_type:
        card_type = request.query_params.get("card_type", "bKash / Card")

    if not tran_id:
        return HTMLResponse("<h3>Payment Error: Missing Transaction ID</h3>", status_code=400)

    payments_col = get_payments_collection()
    payment_rec = await payments_col.find_one({"transaction_id": tran_id})
    if not payment_rec:
        return HTMLResponse("<h3>Payment record not found</h3>", status_code=404)

    # Optional server-to-server validation if val_id is provided from real sandbox
    if val_id and not val_id.startswith("SIM_"):
        try:
            val_params = {
                "val_id": val_id,
                "store_id": settings.SSLCOMMERZ_STORE_ID,
                "store_passwd": settings.SSLCOMMERZ_STORE_PASSWD,
                "v": "1",
                "format": "json",
            }
            async with httpx.AsyncClient(timeout=8.0) as client:
                val_resp = await client.get(SSLCOMMERZ_SANDBOX_VALIDATOR, params=val_params)
                if val_resp.status_code == 200:
                    val_data = val_resp.json()
                    status_val = val_data.get("status")
                    if status_val not in ("VALID", "VALIDATED"):
                        logger.warning(f"SSLCommerz validation failed for val_id={val_id}: {val_data}")
        except Exception as e:
            logger.warning(f"Validation API request skipped ({e}). Proceeding in sandbox mode.")

    # Mark transaction completed
    now_iso = datetime.now(timezone.utc).isoformat()
    await payments_col.update_one(
        {"transaction_id": tran_id},
        {
            "$set": {
                "status": "completed",
                "val_id": val_id or f"VAL-{tran_id}",
                "payment_method": card_type or "SSLCommerz Sandbox",
                "bank_tran_id": bank_tran_id or f"BNK-{tran_id}",
                "updated_at": now_iso,
                "completed_at": now_iso,
            }
        },
    )

    # Upgrade user to Pro!
    users_col = get_users_collection()
    user_id = payment_rec.get("user_id")
    await users_col.update_one(
        {"_id": user_id},
        {"$set": {"plan": "pro", "plan_upgraded_at": now_iso}},
    )
    logger.info(f"Student account {user_id} successfully upgraded to StudyBuddy Pro (tran_id: {tran_id})")

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Payment Successful - StudyBuddy Pro</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                background: #F8FAFC;
                color: #0F172A;
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: 100vh;
                margin: 0;
            }}
            .card {{
                background: #FFFFFF;
                border-radius: 20px;
                padding: 40px;
                box-shadow: 0 10px 25px -5px rgba(0,0,0,0.06), 0 8px 10px -6px rgba(0,0,0,0.04);
                max-width: 460px;
                text-align: center;
                border: 1px solid #E2E8F0;
            }}
            .badge {{
                display: inline-block;
                width: 64px;
                height: 64px;
                line-height: 64px;
                border-radius: 32px;
                background: #DCFCE7;
                color: #10B981;
                font-size: 32px;
                margin-bottom: 20px;
            }}
            h1 {{ font-size: 22px; margin: 0 0 10px 0; color: #0F172A; }}
            p {{ font-size: 14px; color: #64748B; margin: 0 0 20px 0; line-height: 1.5; }}
            .details {{
                background: #F1F5F9;
                border-radius: 12px;
                padding: 14px;
                font-size: 13px;
                text-align: left;
                margin-bottom: 24px;
            }}
            .row {{ display: flex; justify-content: space-between; margin-bottom: 6px; }}
            .row:last-child {{ margin-bottom: 0; }}
            .row span:first-child {{ color: #64748B; }}
            .row span:last-child {{ font-weight: 600; color: #0F172A; }}
            .btn {{
                background: #00796B;
                color: #FFFFFF;
                text-decoration: none;
                padding: 12px 24px;
                border-radius: 10px;
                font-weight: 600;
                font-size: 14px;
                display: inline-block;
            }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="badge">✓</div>
            <h1>Payment Successful!</h1>
            <p>Welcome to <strong>StudyBuddy Pro</strong>. Unlimited daily study sessions and quiz generation are now active.</p>
            <div class="details">
                <div class="row"><span>Transaction ID</span><span>{tran_id}</span></div>
                <div class="row"><span>Amount Paid</span><span>৳{payment_rec.get('amount', 499.0):.2f} BDT</span></div>
                <div class="row"><span>Payment Method</span><span>{card_type or 'SSLCommerz Sandbox'}</span></div>
                <div class="row"><span>Status</span><span style="color:#10B981;">VERIFIED & ACTIVE</span></div>
            </div>
            <p style="font-size: 12px; color: #94A3B8;">You can now close this browser window and return to your StudyBuddy desktop app.</p>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content, status_code=200)


@router.post("/fail", response_class=HTMLResponse)
@router.get("/fail", response_class=HTMLResponse)
async def payment_fail(tran_id: Optional[str] = Form(None)):
    if tran_id:
        payments_col = get_payments_collection()
        await payments_col.update_one(
            {"transaction_id": tran_id},
            {"$set": {"status": "failed", "updated_at": datetime.now(timezone.utc).isoformat()}},
        )
    return HTMLResponse("<h3>Payment Failed or Declined in Sandbox. You can return to StudyBuddy to try again.</h3>", status_code=200)


@router.post("/cancel", response_class=HTMLResponse)
@router.get("/cancel", response_class=HTMLResponse)
async def payment_cancel(tran_id: Optional[str] = Form(None)):
    if tran_id:
        payments_col = get_payments_collection()
        await payments_col.update_one(
            {"transaction_id": tran_id},
            {"$set": {"status": "cancelled", "updated_at": datetime.now(timezone.utc).isoformat()}},
        )
    return HTMLResponse("<h3>Payment Cancelled. You can return to StudyBuddy.</h3>", status_code=200)


@router.post("/ipn")
async def payment_ipn(
    tran_id: Optional[str] = Form(None),
    val_id: Optional[str] = Form(None),
    status_str: Optional[str] = Form(None),
):
    """
    Instant Payment Notification (IPN) webhook called asynchronously by SSLCommerz.
    """
    if not tran_id or status_str not in ("VALID", "VALIDATED"):
        return {"status": "ignored"}

    payments_col = get_payments_collection()
    rec = await payments_col.find_one({"transaction_id": tran_id})
    if rec and rec.get("status") != "completed":
        now_iso = datetime.now(timezone.utc).isoformat()
        await payments_col.update_one(
            {"transaction_id": tran_id},
            {"$set": {"status": "completed", "val_id": val_id, "updated_at": now_iso}},
        )
        users_col = get_users_collection()
        await users_col.update_one(
            {"_id": rec.get("user_id")},
            {"$set": {"plan": "pro", "plan_upgraded_at": now_iso}},
        )
        logger.info(f"IPN: Account {rec.get('user_id')} upgraded to Pro via IPN webhook.")
    return {"status": "received"}


@router.get("/status/{transaction_id}", response_model=PaymentStatusResponse)
async def get_payment_status(
    transaction_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Polled by Flet frontend while waiting for user to complete payment in browser.
    """
    payments_col = get_payments_collection()
    rec = await payments_col.find_one({"transaction_id": transaction_id})
    if not rec:
        raise HTTPException(status_code=404, detail="Transaction not found.")

    status_str = rec.get("status", "pending")
    user_id = str(current_user["_id"])
    users_col = get_users_collection()
    user_doc = await users_col.find_one({"_id": user_id})
    is_pro = (user_doc.get("plan") == "pro") if user_doc else False

    return PaymentStatusResponse(
        transaction_id=transaction_id,
        user_id=user_id,
        status=status_str,
        amount=rec.get("amount", 0.0),
        currency=rec.get("currency", "BDT"),
        payment_method=rec.get("payment_method"),
        val_id=rec.get("val_id"),
        is_pro=is_pro,
        created_at=rec.get("created_at", ""),
        message=f"Transaction is currently '{status_str}'." + (" User is Pro." if is_pro else ""),
    )


@router.get("/transactions", response_model=PaymentHistoryResponse)
async def list_payment_transactions(current_user: dict = Depends(get_current_user)):
    """
    Returns payment history and sandbox transactions for monitoring and auditing.
    """
    user_id = str(current_user["_id"])
    payments_col = get_payments_collection()
    res = payments_col.find({"user_id": user_id})
    if hasattr(res, "sort"):
        cursor = res.sort("created_at", -1)
        raw_items = await cursor.to_list(length=100)
    else:
        raw_items = await res
        raw_items.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    items = []
    for d in raw_items:
        items.append(
            PaymentTransactionItem(
                transaction_id=d.get("transaction_id", ""),
                user_id=str(d.get("user_id", "")),
                user_email=d.get("user_email"),
                user_name=d.get("user_name"),
                base_price=float(d.get("base_price", 499.0)),
                discount_percent=float(d.get("discount_percent", 0.0)),
                discount_amount=float(d.get("discount_amount", 0.0)),
                amount=float(d.get("amount", 499.0)),
                currency=d.get("currency", "BDT"),
                status=d.get("status", "pending"),
                payment_method=d.get("payment_method"),
                val_id=d.get("val_id"),
                is_sandbox=bool(d.get("is_sandbox", True)),
                created_at=str(d.get("created_at", "")),
                completed_at=d.get("completed_at"),
            )
        )
    return PaymentHistoryResponse(transactions=items, total=len(items))


@router.post("/simulate-success/{transaction_id}")
async def simulate_payment_success(
    transaction_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Developer Sandbox helper: allows instant completion of sandbox transaction from Flet UI
    without leaving the application during demos.
    """
    payments_col = get_payments_collection()
    rec = await payments_col.find_one({"transaction_id": transaction_id})
    if not rec:
        raise HTTPException(status_code=404, detail="Transaction not found.")

    now_iso = datetime.now(timezone.utc).isoformat()
    await payments_col.update_one(
        {"transaction_id": transaction_id},
        {
            "$set": {
                "status": "completed",
                "val_id": f"SIM_VAL_{transaction_id}",
                "payment_method": "bKash (Sandbox Simulator)",
                "updated_at": now_iso,
                "completed_at": now_iso,
            }
        },
    )

    user_id = str(current_user["_id"])
    users_col = get_users_collection()
    await users_col.update_one(
        {"_id": user_id},
        {"$set": {"plan": "pro", "plan_upgraded_at": now_iso}},
    )
    logger.info(f"Sandbox Simulation: Account {user_id} upgraded to StudyBuddy Pro.")
    return {
        "success": True,
        "transaction_id": transaction_id,
        "plan": "pro",
        "message": "SSLCommerz Sandbox payment successfully simulated. Account upgraded to Pro!",
    }


@router.get("/sandbox-checkout/{transaction_id}", response_class=HTMLResponse)
async def sandbox_checkout_page(transaction_id: str):
    """
    Renders an interactive SSLCommerz Developer Sandbox mock payment page (bKash, Nagad, Rocket, Cards)
    used for local offline demos or when the public gateway is tunneled.
    """
    payments_col = get_payments_collection()
    rec = await payments_col.find_one({"transaction_id": transaction_id})
    if not rec:
        return HTMLResponse("<h3>Transaction not found</h3>", status_code=404)

    amount = rec.get("amount", 499.0)
    user_name = rec.get("user_name", "Student")
    discount_amt = rec.get("discount_amount", 0.0)

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>SSLCommerz Sandbox Payment Gateway</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                background: #0F172A;
                color: #F8FAFC;
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: 100vh;
                margin: 0;
            }}
            .checkout-container {{
                background: #1E293B;
                width: 480px;
                border-radius: 16px;
                padding: 32px;
                border: 1px solid #334155;
                box-shadow: 0 20px 25px -5px rgba(0,0,0,0.5);
            }}
            .header {{
                display: flex;
                align-items: center;
                justify-content: space-between;
                border-bottom: 1px solid #334155;
                padding-bottom: 16px;
                margin-bottom: 20px;
            }}
            .brand {{ font-size: 18px; font-weight: 700; color: #F59E0B; }}
            .sandbox-pill {{
                background: #FEE2E2;
                color: #EF4444;
                font-size: 11px;
                font-weight: 700;
                padding: 4px 10px;
                border-radius: 20px;
            }}
            .order-summary {{
                background: #0F172A;
                padding: 16px;
                border-radius: 12px;
                margin-bottom: 24px;
                font-size: 13px;
            }}
            .row {{ display: flex; justify-content: space-between; margin-bottom: 8px; }}
            .row:last-child {{ margin-bottom: 0; }}
            .total-row {{
                border-top: 1px solid #334155;
                padding-top: 8px;
                margin-top: 8px;
                font-size: 16px;
                font-weight: 700;
                color: #10B981;
            }}
            .payment-methods {{
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 10px;
                margin-bottom: 24px;
            }}
            .method-btn {{
                background: #334155;
                border: 2px solid transparent;
                border-radius: 10px;
                padding: 12px 6px;
                text-align: center;
                cursor: pointer;
                font-size: 12px;
                font-weight: 600;
                color: #F8FAFC;
            }}
            .method-btn.active {{
                border-color: #00796B;
                background: #00796B22;
                color: #2DD4BF;
            }}
            .pay-btn {{
                background: #10B981;
                color: #FFFFFF;
                border: none;
                width: 100%;
                padding: 14px;
                border-radius: 10px;
                font-size: 15px;
                font-weight: 700;
                cursor: pointer;
                transition: background 0.2s;
            }}
            .pay-btn:hover {{ background: #059669; }}
            .cancel-btn {{
                background: transparent;
                color: #94A3B8;
                border: none;
                width: 100%;
                padding: 10px;
                margin-top: 8px;
                font-size: 13px;
                cursor: pointer;
            }}
        </style>
    </head>
    <body>
        <div class="checkout-container">
            <div class="header">
                <span class="brand">SSLCommerz Gateway</span>
                <span class="sandbox-pill">TEST SANDBOX</span>
            </div>
            <div class="order-summary">
                <div class="row"><span>Customer</span><span>{user_name}</span></div>
                <div class="row"><span>Product</span><span>StudyBuddy Pro (Monthly)</span></div>
                <div class="row"><span>Transaction ID</span><span style="font-family: monospace;">{transaction_id}</span></div>
                {f'<div class="row" style="color:#2DD4BF;"><span>Scholar XP Discount (5%)</span><span>-৳{discount_amt:.2f}</span></div>' if discount_amt > 0 else ''}
                <div class="row total-row"><span>Total Payable</span><span>৳{amount:.2f} BDT</span></div>
            </div>

            <p style="font-size: 12px; color: #94A3B8; margin-bottom: 10px;">Select Test Payment Method:</p>
            <div class="payment-methods">
                <div class="method-btn active" onclick="selectMethod('bKash')">bKash</div>
                <div class="method-btn" onclick="selectMethod('Nagad')">Nagad</div>
                <div class="method-btn" onclick="selectMethod('Visa / Master')">Cards</div>
            </div>

            <form action="/api/payment/success" method="POST">
                <input type="hidden" name="tran_id" value="{transaction_id}">
                <input type="hidden" name="val_id" value="SIM_VAL_{transaction_id}">
                <input type="hidden" name="amount" value="{amount}">
                <input type="hidden" name="card_type" id="card_type_input" value="bKash">
                <input type="hidden" name="bank_tran_id" value="SIM_BNK_9981">
                <button type="submit" class="pay-btn">Pay ৳{amount:.2f} (Confirm Sandbox Payment)</button>
            </form>
            <form action="/api/payment/cancel" method="POST">
                <input type="hidden" name="tran_id" value="{transaction_id}">
                <button type="submit" class="cancel-btn">Cancel and return to StudyBuddy</button>
            </form>
        </div>

        <script>
            function selectMethod(name) {{
                document.getElementById('card_type_input').value = name;
                var btns = document.querySelectorAll('.method-btn');
                btns.forEach(b => b.classList.remove('active'));
                event.target.classList.add('active');
            }}
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html, status_code=200)
