import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import requests
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration
JOTFORM_API_KEY = os.getenv('JOTFORM_API_KEY')
JOTFORM_FORM_ID = os.getenv('JOTFORM_FORM_ID')
DB_PATH = 'lendermatch_deals.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS deals (
            id INTEGER PRIMARY KEY,
            jotform_submission_id TEXT UNIQUE,
            borrower_name TEXT,
            deal_amount REAL,
            property_address TEXT,
            loan_type TEXT,
            submission_date TEXT,
            status TEXT DEFAULT 'Submitted',
            due_diligence_date TEXT,
            preapproval_date TEXT,
            term_sheet_date TEXT,
            approval_date TEXT,
            closing_date TEXT,
            title_company TEXT,
            notes TEXT,
            last_updated TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS lenders (
            id INTEGER PRIMARY KEY,
            lender_name TEXT,
            company TEXT,
            min_loan REAL,
            max_loan REAL,
            preferred_types TEXT,
            preferred_states TEXT,
            contact_email TEXT,
            contact_phone TEXT,
            notes TEXT,
            active INTEGER DEFAULT 1
        )
    ''')
    conn.commit()
    conn.close()

def add_sample_lenders():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    sample_lenders = [
        ("Private Lender A", "NCP Network", 500000, 5000000, "Bridge,Construction", "IL,IN,AZ", "lenderA@NCP.com", "312-555-0101", "Fast close", 1),
        ("Equity Partner B", "MidPoint Capital", 2000000, 50000000, "Equity,JV", "US", "partnerB@example.com", "602-555-0202", "High LTV", 1),
    ]
    for lender in sample_lenders:
        cursor.execute('''
            INSERT OR IGNORE INTO lenders 
            (lender_name, company, min_loan, max_loan, preferred_types, preferred_states, contact_email, contact_phone, notes, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', lender)
    conn.commit()
    conn.close()

def fetch_jotform_submissions():
    if not JOTFORM_API_KEY or not JOTFORM_FORM_ID:
        st.warning("Jotform credentials not set")
        return []
    url = f"https://api.jotform.com/form/{JOTFORM_FORM_ID}/submissions"
    headers = {'APIKEY': JOTFORM_API_KEY}
    params = {'limit': 100, 'order_by': 'created_at,desc'}
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json().get('content', [])
    except Exception as e:
        st.error(f"Error fetching Jotform: {e}")
        return []

def get_answer(answers, possible_keys):
    for qid, answer in answers.items():
        text = str(answer.get('text', '')).lower()
        name = str(answer.get('name', '')).lower()
        for key in possible_keys:
            if key.lower() in text or key.lower() in name:
                return answer.get('answer', '')
    return ''

def save_deal(submission):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    submission_id = submission.get('id')
    answers = submission.get('answers', {})
    
    borrower_name = get_answer(answers, ['name', 'borrowerName', 'fullName'])
    deal_amount = get_answer(answers, ['loanAmount', 'dealAmount', 'amount'])
    property_address = get_answer(answers, ['propertyAddress', 'address'])
    loan_type = get_answer(answers, ['loanType', 'dealType'])
    
    try:
        deal_amount = float(str(deal_amount).replace(',', '').replace('$', '')) if deal_amount else 0
    except:
        deal_amount = 0
    
    current_time = datetime.now().isoformat()
    
    cursor.execute('''
        INSERT INTO deals (jotform_submission_id, borrower_name, deal_amount, property_address, loan_type, submission_date, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(jotform_submission_id) DO UPDATE SET last_updated = excluded.last_updated
    ''', (submission_id, borrower_name, deal_amount, property_address, loan_type, current_time, current_time))
    
    conn.commit()
    conn.close()

def match_lenders(deal):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lenders WHERE active = 1")
    lenders = cursor.fetchall()
    conn.close()
    
    matches = []
    deal_amount = deal.get('deal_amount', 0)
    loan_type = str(deal.get('loan_type', '')).lower()
    
    for lender in lenders:
        lender_dict = dict(lender)
        if lender_dict['min_loan'] <= deal_amount <= lender_dict['max_loan']:
            types = [t.strip().lower() for t in lender_dict['preferred_types'].split(',')]
            if any(t in loan_type for t in types) or not types:
                matches.append(lender_dict)
    return matches

def update_deal_status(deal_id, new_status, dates=None, title_company='', notes=''):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    current_time = datetime.now().isoformat()
    
    updates = {'status': new_status, 'last_updated': current_time}
    if dates:
        for k, v in dates.items():
            updates[k] = v
    if title_company:
        updates['title_company'] = title_company
    if notes:
        updates['notes'] = notes
    
    set_clause = ', '.join([f"{k}=?" for k in updates.keys()])
    values = list(updates.values())
    values.append(deal_id)
    
    cursor.execute(f"UPDATE deals SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()

def main():
    st.set_page_config(page_title="LenderMatch - NCP", layout="wide")
    st.title("🌟 LenderMatch Deal Pipeline")
    st.markdown("**National Capital Partnerships** - Real Estate Private Lending")
    
    init_db()
    add_sample_lenders()
    
    st.sidebar.header("🔧 Controls")
    if st.sidebar.button("🔄 Pull New Jotform Submissions"):
        submissions = fetch_jotform_submissions()
        for sub in submissions:
            save_deal(sub)
        st.success(f"✅ Processed {len(submissions)} new submissions!")
    
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Pipeline", "✏️ Update Deal", "🔍 Match Lenders", "👥 Lenders"])
    
    with tab1:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("SELECT id, borrower_name, deal_amount, property_address, loan_type, status, submission_date, last_updated FROM deals ORDER BY submission_date DESC", conn)
        conn.close()
        if not df.empty:
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No deals yet. Pull from Jotform.")
    
    with tab2:
        st.subheader("Update Deal")
        deal_id = st.number_input("Deal ID", min_value=1, step=1)
        new_status = st.selectbox("Status", ["Submitted", "Due Diligence", "Preapproval", "Term Sheet", "Approval", "Closing Date Set", "Title Company Assigned"])
        dd_date = st.date_input("Due Diligence Date", value=None)
        pre_date = st.date_input("Preapproval Date", value=None)
        ts_date = st.date_input("Term Sheet Date", value=None)
        closing_date = st.date_input("Closing Date", value=None)
        title_co = st.text_input("Title Company")
        notes = st.text_area("Notes")
        if st.button("Update Deal"):
            dates = {}
            if dd_date: dates['due_diligence_date'] = str(dd_date)
            if pre_date: dates['preapproval_date'] = str(pre_date)
            if ts_date: dates['term_sheet_date'] = str(ts_date)
            if closing_date: dates['closing_date'] = str(closing_date)
            update_deal_status(deal_id, new_status, dates, title_co, notes)
            st.success(f"✅ Deal {deal_id} updated!")
    
    with tab3:
        st.subheader("🔍 Lender Matching")
        conn = sqlite3.connect(DB_PATH)
        deals = pd.read_sql_query("SELECT * FROM deals", conn)
        conn.close()
        if not deals.empty:
            selected = st.selectbox("Select Deal", deals['id'].tolist(), format_func=lambda x: f"ID {x} - {deals[deals['id']==x]['borrower_name'].iloc[0]}")
            deal_row = deals[deals['id'] == selected].iloc[0]
            matches = match_lenders(deal_row.to_dict())
            st.write("**Matching Lenders:**")
            if matches:
                st.dataframe(pd.DataFrame(matches))
            else:
                st.warning("No matches found for this deal.")
        else:
            st.info("No deals yet")
    
    with tab4:
        st.subheader("Manage Lenders")
        with st.form("add_lender"):
            name = st.text_input("Lender Name")
            company = st.text_input("Company")
            minl = st.number_input("Min Loan $", 50000)
            maxl = st.number_input("Max Loan $", 10000000)
            types = st.text_input("Preferred Types (comma separated)", "Bridge,Construction,Equity")
            states = st.text_input("Preferred States", "IL,IN,AZ")
            email = st.text_input("Contact Email")
            if st.form_submit_button("Add Lender"):
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute('''INSERT INTO lenders 
                (lender_name, company, min_loan, max_loan, preferred_types, preferred_states, contact_email, active)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)''', (name, company, minl, maxl, types, states, email))
                conn.commit()
                conn.close()
                st.success("Lender added successfully!")

if __name__ == "__main__":
    main()