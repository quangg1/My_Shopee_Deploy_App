from flask import Flask, render_template, request, redirect, url_for, session
import requests
import concurrent.futures
from datetime import datetime, timedelta
import re

app = Flask(__name__)
app.secret_key = 'secret_key_for_session'

# ==== Hàm trích xuất số từ chuỗi ====
def extract_number(value):
    """Trích xuất phần số từ chuỗi, bỏ ký tự không liên quan."""
    try:
        return float(re.sub(r"[^\d.]", "", str(value))) if re.sub(r"[^\d.]", "", str(value)) else 0
    except:
        return 0

# ==== Hàm lấy danh sách session ID theo ngày ====
def fetch_live_sessions(cookies, days_ago):
    base_url = "https://creator.shopee.vn/supply/api/lm/sellercenter/liveList/v2"
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    all_sessions = []

    def get_sessions_for_day(i):
        date_str = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        params = {
            "page": 1,
            "pageSize": 10,
            "name": "",
            "orderBy": "",
            "sort": "",
            "timeDim": "1d",
            "endDate": date_str  # Chỉ lấy dữ liệu trong ngày đó
        }
        response = requests.get(base_url, params=params, headers=headers, cookies=cookies)
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 0 and "list" in data.get("data", {}):
                return [live["sessionId"] for live in data["data"]["list"]]
        return []

    with concurrent.futures.ThreadPoolExecutor() as executor:
        results = executor.map(get_sessions_for_day, range(0, days_ago + 1))

    for result in results:
        all_sessions.extend(result)

    return all_sessions

# ==== Hàm lấy danh sách sản phẩm từ Shopee ====
def fetch_shopee_products(cookies, sessionId):
    base_url = "https://creator.shopee.vn/supply/api/lm/sellercenter/realtime/dashboard/productList?"
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

    params = {
        "sessionId": sessionId,
        "productName": "",
        "productListTimeRange": 0,
        "productListOrderBy": "itemSold",
        "sort": "asc",
        "page": 1,
        "pageSize": 10
    }

    # Lấy số trang tổng cộng
    response = requests.get(base_url, params=params, headers=headers, cookies=cookies)
    if response.status_code != 200:
        return []

    data = response.json()
    if data.get("code") != 0 or not data.get("data"):
        return []

    total_pages = data["data"]["totalPage"]
    all_products = []

    def fetch_page(page):
        """Hàm lấy dữ liệu của từng trang"""
        params["page"] = page
        response = requests.get(base_url, params=params, headers=headers, cookies=cookies)
        if response.status_code == 200:
            page_data = response.json()
            if page_data.get("code") == 0 and page_data.get("data"):
                return page_data["data"]["list"]
        return []

    # Chạy đa luồng để lấy dữ liệu của từng trang
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(fetch_page, range(1, total_pages + 1)))

    # Ghép toàn bộ dữ liệu sản phẩm lại
    all_products = [product for sublist in results for product in sublist]

    # Xử lý dữ liệu sản phẩm
    return [
        {
            "Index": i + 1,
            "ID": product.get("itemId", "N/A"),
            "Tên sản phẩm": product.get("title", "Không có tên"),
            "Giá thấp nhất": extract_number(product.get("minPrice", "N/A")),
            "Giá cao nhất": extract_number(product.get("maxPrice", "N/A")),
            "Số lần nhấp chuột": product.get("productClicks", 0),
            "CTR (%)": product.get("ctr", 0.0),
            "Số lượt thêm vào giỏ": product.get("atc", 0),
            "Đơn hàng tạo ra": product.get("ordersCreated", 0),
            "Doanh thu": product.get("revenue", 0.0),
            "Số lượng bán": product.get("itemSold", 0),
            "COR (%)": product.get("cor", 0.0),
            "Đơn hàng xác nhận": product.get("confirmedOrderCnt", 0),
            "Doanh thu xác nhận": product.get("confirmedRevenue", 0.0),
            "Số lượng bán xác nhận": product.get("confirmedItemSold", 0),
            "COR xác nhận (%)": product.get("confirmedCor", 0.0),
            "Link Shopee": f'https://affiliate.shopee.vn/offer/product_offer/{product["itemId"]}'
        }
        for i, product in enumerate(all_products)
    ]

# ==== Route cho trang nhập cookies ====
@app.route("/", methods=["POST", "GET"])
def index():
    if request.method == "POST":
        cookies_input = request.form["cookies"]
        session["cookies"] = {"Cookie": cookies_input}
        return redirect(url_for("index"))  # Điều hướng về trang nhập cookies sau khi lưu cookies

    if "cookies" not in session:
        return render_template("index.html")  # Nếu chưa có cookies, yêu cầu nhập cookies

    return render_template("index.html")

# ==== Route lấy dữ liệu sản phẩm ====
@app.route("/fetch_products", methods=["POST"])
def fetch_products():
    cookies = session.get("cookies")
    session_id = request.form.get("session_id")
    days_ago = request.form.get("days_ago")

    # Nếu days_ago không phải số, mặc định là 7 ngày
    if days_ago is not None and days_ago.isdigit():
        days_ago = int(days_ago)
    else:
        days_ago = 7

    option = request.form.get("option")
    
    products = []
    if option == "Nhập sessionId" and session_id:
        products = fetch_shopee_products(cookies, session_id)
    elif option == "Lấy theo số ngày" and days_ago:
        session_ids = fetch_live_sessions(cookies, days_ago)
        for sid in session_ids:
            products.extend(fetch_shopee_products(cookies, sid))

    return render_template("results.html", products=products)

if __name__ == "__main__":
    app.run(debug=True)
