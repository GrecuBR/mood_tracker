from flask import Flask, render_template, redirect, url_for, request, session, flash, send_file, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, csv, io
from datetime import datetime
import os
import flask
from datetime import datetime


app = Flask(__name__)



app.secret_key = 'supersecretkey'

DB_NAME = 'mood.db'


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS moods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            date TEXT,
            mood TEXT,
            note TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    conn.commit()
    conn.close()


# @app.before_first_request
def create_tables():
    init_db()



@app.template_filter('datetime_format')
def datetime_format(value):
    try:
        # Try parsing the ISO datetime format: '2025-09-28T14:30'
        dt = datetime.strptime(value, "%Y-%m-%dT%H:%M")
        return dt.strftime("%b %d, %Y at %I:%M %p")  # e.g., Sep 28, 2025 at 02:30 PM
    except Exception:
        return value  # Fallback if parsing fails

# Authentication Routes
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])

        try:
            conn = sqlite3.connect(DB_NAME)
            cur = conn.cursor()
            cur.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            conn.commit()
            conn.close()

            # AJAX response
            if request.accept_mimetypes['application/json']:
                return jsonify({'success': True, 'message': 'Registered successfully. Please log in.'})

            flash('Registered successfully. Please log in.')
            return redirect(url_for('login'))

        except:
            if request.accept_mimetypes['application/json']:
                return jsonify({'success': False, 'message': 'Username already taken.'})

            flash('Username already taken.')

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        cur.execute("SELECT id, password FROM users WHERE username = ?", (username,))
        user = cur.fetchone()
        conn.close()

        if user and check_password_hash(user[1], password):
            session['user_id'] = user[0]
            session['username'] = username

            # AJAX login
            if request.accept_mimetypes['application/json']:
                return jsonify({'success': True, 'message': 'Login successful'})

            return redirect(url_for('dashboard'))

        # Failed login
        if request.accept_mimetypes['application/json']:
            return jsonify({'success': False, 'message': 'Invalid credentials'})

        flash('Invalid credentials.')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/delete_account')
def delete_account():
    user_id = session.get('user_id')
    if user_id:
        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        cur.execute("DELETE FROM moods WHERE user_id = ?", (user_id,))
        cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
    return redirect(url_for('logout'))


# Mood Entry Routes
@app.route('/')
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT id, date, mood, note FROM moods WHERE user_id = ? ORDER BY date DESC", (user_id,))
    moods = cur.fetchall()
    conn.close()

    return render_template('dashboard.html', moods=moods)


@app.route('/add', methods=['GET', 'POST'])
def add_entry():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        data = request.form
        date = data.get('date')
        mood = data.get('mood')
        note = data.get('note')

        if not date or not mood:
            return flask.jsonify({'success': False, 'message': 'Date and mood are required.'}), 400

        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        cur.execute("INSERT INTO moods (user_id, date, mood, note) VALUES (?, ?, ?, ?)",
                    (session['user_id'], date, mood, note))
        conn.commit()
        conn.close()

        return flask.jsonify({'success': True, 'message': 'Mood entry saved!'}), 200

    return render_template('add_entry.html')



@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_entry(id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    if request.method == 'POST':
        date = request.form['date']
        mood = request.form['mood']
        note = request.form['note']

        cur.execute("UPDATE moods SET date = ?, mood = ?, note = ? WHERE id = ?", (date, mood, note, id))
        conn.commit()
        conn.close()

        # Check if it's an AJAX request
        if request.accept_mimetypes['application/json']:
            return jsonify({'success': True, 'message': 'Mood updated successfully.'})
        else:
            return redirect(url_for('dashboard'))

    cur.execute("SELECT date, mood, note FROM moods WHERE id = ?", (id,))
    entry = cur.fetchone()
    conn.close()
    return render_template('edit_entry.html', entry=entry, id=id)



@app.route('/delete/<int:id>', methods=['GET', 'DELETE'])
def delete_entry(id):
    if request.method == 'DELETE':
        try:
            conn = sqlite3.connect(DB_NAME)
            cur = conn.cursor()
            cur.execute("DELETE FROM moods WHERE id = ?", (id,))
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'message': 'Entry deleted.'})
        except Exception as e:
            return jsonify({'success': False, 'message': 'Failed to delete entry.'}), 500
    else:
        # Fallback for non-JS navigation
        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        cur.execute("DELETE FROM moods WHERE id = ?", (id,))
        conn.commit()
        conn.close()
        return redirect(url_for('dashboard'))



@app.route('/export')
def export_csv():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT date, mood, note FROM moods WHERE user_id = ?", (session['user_id'],))
    data = cur.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Mood', 'Note'])
    writer.writerows(data)
    output.seek(0)

    return send_file(io.BytesIO(output.read().encode()), mimetype='text/csv', as_attachment=True,
                     download_name='mood_log.csv')


if __name__ == '__main__':
    init_db()
    app.run(debug=True)
