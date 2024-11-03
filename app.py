from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import hashlib
import random
from datetime import datetime  # Импортируйте datetime
from werkzeug.security import generate_password_hash, check_password_hash


app = Flask(__name__)


app.secret_key = 'your_secret_key'

users = {
    'username': {
        'password': generate_password_hash('old_password')
    }
}

DATABASE = '/home/zhenyawallet/mysite/wallet.db'

def init_db():
    conn = sqlite3.connect('/home/zhenyawallet/mysite/database.db')
    c = conn.cursor()

   
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    ''')

    
    c.execute('''
        CREATE TABLE IF NOT EXISTS staking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            currency TEXT NOT NULL,
            staked_amount REAL NOT NULL,
            reward_rate REAL NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    conn.commit()
    conn.close()

def alter_transactions_table():
    
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        try:
            c.execute("ALTER TABLE transactions ADD COLUMN recipient_wallet TEXT")
            conn.commit()
            print("Столбец recipient_wallet успешно добавлен в таблицу transactions.")
        except sqlite3.OperationalError:
            print("Столбец recipient_wallet уже существует.")


def generate_wallet_address():
    
    return hashlib.sha256(str(random.getrandbits(256)).encode()).hexdigest()

def get_user_info(wallet_address):
    
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        user_info = c.execute("SELECT username FROM users WHERE wallet_address = ?", (wallet_address,)).fetchone()
        return user_info if user_info else None

@app.template_filter('datetimeformat')
def datetimeformat(value):
    
    if isinstance(value, str):
        return datetime.strptime(value, '%Y-%m-%d %H:%M:%S').strftime('%d-%m-%Y %H:%M:%S')
    return value

@app.route('/')
def home():
    if 'username' in session:
        username = session['username']
        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()
            user_info = c.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            return render_template('home.html', user_info=user_info)
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()
            user = c.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password)).fetchone()
            if user:
                session['username'] = username
                session['user_id'] = user[0]
                return redirect(url_for('home'))
            else:
                flash('Неверные учетные данные! Попробуйте снова.')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    print("Функция регистрации вызвана")  
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        wallet_address = generate_wallet_address()  

        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()
            try:
                c.execute("INSERT INTO users (username, password, wallet_address) VALUES (?, ?, ?)",
                           (username, password, wallet_address))
                conn.commit()
                flash('Регистрация успешна! Вы можете войти в систему.')
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                flash('Это имя пользователя уже занято. Попробуйте другое.')
                print(f"Ошибка: {username} уже существует")  
            except Exception as e:
                print(f"Ошибка при регистрации: {str(e)}")  
    return render_template('register.html')


@app.route('/stake', methods=['GET', 'POST'])
def stake():
    user_id = session.get('user_id')
    if user_id is None:
        flash('Пожалуйста, войдите в систему.', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        currency = request.form.get('currency')
        amount = float(request.form.get('amount'))
        duration = int(request.form.get('duration'))  
        reward_rate = 0.05  

        
        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()
            balance = c.execute(f"SELECT balance_{currency} FROM users WHERE id = ?", (user_id,)).fetchone()[0]

            if balance < amount:
                flash('Недостаточно средств для стейкинга!', 'error')
                return redirect(url_for('stake'))

            
            c.execute(f"UPDATE users SET balance_{currency} = balance_{currency} - ? WHERE id = ?", (amount, user_id))

            
            start_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            end_date = (datetime.now() + timedelta(days=duration)).strftime('%Y-%m-%d %H:%M:%S')

            
            c.execute('''INSERT INTO staking (user_id, currency, staked_amount, reward_rate, start_date, end_date)
                         VALUES (?, ?, ?, ?, ?, ?)''', (user_id, currency, amount, reward_rate, start_date, end_date))

            conn.commit()

        flash(f'Вы успешно застейкали {amount} {currency} на {duration} дней!')
        return redirect(url_for('home'))

    return render_template('stake.html')


@app.route('/claim_rewards', methods=['POST'])
def claim_rewards():
    user_id = session.get('user_id')
    staking_id = request.form.get('staking_id')

    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        
        staking_info = c.execute('''SELECT staked_amount, reward_rate, currency, start_date, end_date
                                    FROM staking WHERE id = ? AND user_id = ? AND status = 'active' ''',
                                    (staking_id, user_id)).fetchone()

        if staking_info:
            staked_amount, reward_rate, currency, start_date, end_date = staking_info

            
            if datetime.now() >= datetime.strptime(end_date, '%Y-%m-%d %H:%M:%S'):
                
                reward = staked_amount * reward_rate

                
                c.execute(f"UPDATE users SET balance_{currency} = balance_{currency} + ? WHERE id = ?", (reward, user_id))

                
                c.execute("UPDATE staking SET status = 'completed' WHERE id = ?", (staking_id,))

                conn.commit()
                flash(f'Вы успешно получили вознаграждение: {reward} {currency}!')
            else:
                flash('Стейкинг еще не завершен!', 'error')
        else:
            flash('Стейкинг не найден!', 'error')

    return redirect(url_for('home'))



@app.route('/delete_account', methods=['POST'])
def delete_account():
    user_id = session.get('user_id')

    if user_id is None:
        flash('Вы не вошли в систему. Пожалуйста, войдите заново.', 'error')
        return redirect(url_for('login'))

    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        try:
            
            c.execute("DELETE FROM transactions WHERE user_id = ?", (user_id,))
            
            c.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
            session.pop('username', None)
            session.pop('user_id', None)
            flash('Ваш аккаунт был успешно удален!', 'success')
            return redirect(url_for('register'))
        except sqlite3.Error as e:
            flash(f'Ошибка при удалении аккаунта: {str(e)}', 'error')
            return redirect(url_for('settings'))

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        new_username = request.form.get('new_username')
        old_password = request.form.get('old_password').strip()  
        new_password = request.form.get('new_password').strip()  

        
        if new_username:
            flash('Имя пользователя обновлено', 'success')  

        
        if old_password and new_password:
            print("Введенный старый пароль:", old_password)  
            print("Хэш старого пароля в базе данных:", users['username']['password'])  

            if check_password_hash(users['username']['password'], old_password):
                users['username']['password'] = generate_password_hash(new_password)
                flash('Пароль обновлен', 'success')
            else:
                flash('Старый пароль неверен', 'danger')

    return render_template('settings.html')

@app.route('/update_password', methods=['POST'])
def update_password():
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    
    if check_password_hash(users['username'], current_password):
        if new_password == confirm_password:
            # Обновление пароля (зашифровываем и сохраняем)
            users['username'] = generate_password_hash(new_password)
            flash('Пароль успешно обновлен', 'success')
        else:
            flash('Новые пароли не совпадают', 'danger')
    else:
        flash('Неверный текущий пароль', 'danger')

    return redirect(url_for('settings'))

@app.route('/update_username', methods=['POST'])
def update_username():
    user_id = session.get('user_id')  
    new_username = request.form['new_username']

    if user_id is None:
        flash('Вы не вошли в систему. Пожалуйста, войдите заново.', 'error')
        return redirect(url_for('login'))

    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        try:
            c.execute("UPDATE users SET username = ? WHERE id = ?", (new_username, user_id))
            conn.commit()
            session['username'] = new_username  
            flash('Имя пользователя успешно изменено!', 'success')
        except sqlite3.IntegrityError:
            flash('Это имя пользователя уже занято. Попробуйте другое.', 'error')

    return redirect(url_for('settings'))

@app.route('/top_up', methods=['GET', 'POST'])
def top_up():
    if request.method == 'POST':
        currency = request.form.get('currency')
        amount = float(request.form.get('amount'))
        user_id = session.get('user_id')

        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()
            if currency == 'ZhenyaCoin':
                c.execute("UPDATE users SET balance_zhenyacoin = balance_zhenyacoin + ? WHERE id = ?", (amount, user_id))
            elif currency == 'Bitcoin':
                c.execute("UPDATE users SET balance_bitcoin = balance_bitcoin + ? WHERE id = ?", (amount, user_id))
            elif currency == 'Ethereum':
                c.execute("UPDATE users SET balance_ethereum = balance_ethereum + ? WHERE id = ?", (amount, user_id))
            elif currency == 'USDT':
                c.execute("UPDATE users SET balance_usdt = balance_usdt + ? WHERE id = ?", (amount, user_id))
            elif currency == 'TON':
                c.execute("UPDATE users SET balance_ton = balance_ton + ? WHERE id = ?", (amount, user_id))
            elif currency == 'Makscoin':  # Добавляем Makscoin
                c.execute("UPDATE users SET balance_makscoin = balance_makscoin + ? WHERE id = ?", (amount, user_id))

            c.execute("INSERT INTO transactions (user_id, amount, currency, transaction_type) VALUES (?, ?, ?, 'Пополнение')", (user_id, amount, currency))
            conn.commit()
            flash('Баланс успешно пополнен!')
            return redirect(url_for('home'))
    return render_template('top_up.html')

@app.route('/transfer', methods=['GET', 'POST'])
def transfer():
    
    user_id = session.get('user_id')
    if user_id is None:
        flash('Вы вышли из под аккаунта. Пожалуйста, войдите заново.', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        recipient_wallet = request.form.get('recipient_wallet')
        amount = request.form.get('amount')
        currency = request.form.get('currency')

        
        if not recipient_wallet or not amount or not currency:
            flash('Пожалуйста, заполните все поля!')
            return redirect(url_for('transfer'))

        try:
            amount = float(amount)  
        except ValueError:
            flash('Введите корректную сумму!')
            return redirect(url_for('transfer'))

        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()

            
            user_balance_query = f"SELECT balance_{currency.lower()} FROM users WHERE id = ?"
            user_balance = c.execute(user_balance_query, (user_id,)).fetchone()

            if user_balance is None:
                flash('Пользователь не найден!')
                return redirect(url_for('transfer'))

            user_balance = user_balance[0]

            
            if user_balance >= amount:
                
                recipient_query = "SELECT id FROM users WHERE wallet_address = ?"
                recipient_id = c.execute(recipient_query, (recipient_wallet,)).fetchone()

                if recipient_id is None:
                    flash('Получатель не найден!')
                    return redirect(url_for('transfer'))

                
                c.execute(f"UPDATE users SET balance_{currency.lower()} = balance_{currency.lower()} - ? WHERE id = ?", (amount, user_id))
                
                c.execute(f"UPDATE users SET balance_{currency.lower()} = balance_{currency.lower()} + ? WHERE id = ?", (amount, recipient_id[0]))

                
                c.execute("INSERT INTO transactions (user_id, amount, currency, transaction_type, recipient_wallet) VALUES (?, ?, ?, 'Перевод', ?)", (user_id, amount, currency, recipient_wallet))

                conn.commit()  
                flash(f'Перевод {amount} {currency} на кошелек {recipient_wallet} выполнен успешно!')
            else:
                flash('Недостаточно средств для перевода!')

        return redirect(url_for('home'))

    return render_template('transfer.html')


@app.route('/transaction_history')
def transaction_history():
    user_id = session.get('user_id')
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        
        transactions = c.execute('''
            SELECT t.id, sender.username AS sender_name, receiver.username AS receiver_name,
                   t.amount, t.currency, t.transaction_type
            FROM transactions t
            JOIN users sender ON t.user_id = sender.id
            LEFT JOIN users receiver ON t.recipient_wallet = receiver.wallet_address
            WHERE t.user_id = ? OR t.recipient_wallet IN (SELECT wallet_address FROM users WHERE id = ?)
        ''', (user_id, user_id)).fetchall()
    return render_template('transaction_history.html', transactions=transactions)

user_data = {
    'username': 'Имя пользователя',  
    'profile_image': 'profile_image.png',  
}

@app.route('/profile')
def profile():
    
    user_info = [None, user_data['username'], user_data['profile_image']]

    return render_template('profile.html', user_info=user_info)

@app.route('/get-started')
def get_started():
    return render_template('get_started.html')

@app.route('/exchange', methods=['GET', 'POST'])
def exchange():
    if request.method == 'POST':
        user_id = session.get('user_id')
        from_currency = request.form.get('from_currency')
        to_currency = request.form.get('to_currency')
        amount = float(request.form.get('amount'))

        
        exchange_rates = {
            'zhenyacoin': 1.0,  # Обменный курс для ZhenyaCoin
            'bitcoin': 50000.0,  # 1 BTC = 50000 ZHY
            'ethereum': 4000.0,  # 1 ETH = 4000 ZHY
            'usdt': 1.0,        # 1 USDT = 1 ZHY
            'ton': 0.5,        # 1 TON = 0.5 ZHY
        }

        if from_currency not in exchange_rates or to_currency not in exchange_rates:
            flash('Неверная валюта для обмена!')
            return redirect(url_for('exchange'))

        
        user_balance_query = f"SELECT balance_{from_currency} FROM users WHERE id = ?"
        user_balance = sqlite3.connect(DATABASE).execute(user_balance_query, (user_id,)).fetchone()

        if user_balance is None or user_balance[0] < amount:
            flash('Недостаточно средств для обмена!')
            return redirect(url_for('exchange'))

        
        amount_in_to_currency = (amount * exchange_rates[from_currency]) / exchange_rates[to_currency]

        
        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()
            c.execute(f"UPDATE users SET balance_{from_currency} = balance_{from_currency} - ? WHERE id = ?", (amount, user_id))
            c.execute(f"UPDATE users SET balance_{to_currency} = balance_{to_currency} + ? WHERE id = ?", (amount_in_to_currency, user_id))
            conn.commit()

        flash(f'Успешно обменяно {amount} {from_currency} на {amount_in_to_currency} {to_currency}!')
        return redirect(url_for('home'))

    return render_template('exchange.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('user_id', None)
    flash('Вы вышли из системы.')
    return redirect(url_for('login'))

if __name__ == '__main__':
    init_db()  
    app.run(debug=True)
