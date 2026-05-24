import os
from flask import Flask, render_template, redirect, url_for, request, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from google import genai
from PIL import Image
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'cano_ders_platformu_super_gizli_anahtar_123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///platform.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.relationship('Note', backref='author', lazy=True, cascade='all, delete-orphan')


class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    student_class = db.Column(db.String(20), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    content = db.Column(db.Text, nullable=False)
    summary = db.Column(db.Text, nullable=True)
    image_path = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


with app.app_context():
    db.create_all()


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if len(username) < 3:
            flash('Kullanıcı adı en az 3 karakter olmalıdır.', 'danger')
            return redirect(url_for('register'))
        if len(password) < 6:
            flash('Şifre en az 6 karakter olmalıdır.', 'danger')
            return redirect(url_for('register'))

        if User.query.filter_by(username=username).first():
            flash('Bu kullanıcı adı zaten alınmış!', 'danger')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password, method='scrypt')
        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()

        flash('Hesabın başarıyla oluşturuldu! Giriş yapabilirsin.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['username'] = user.username
            flash(f'Hoş geldin, {user.username}! 👋', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Kullanıcı adı veya şifre hatalı!', 'danger')
    return render_template('login.html')


@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        student_class = request.form.get('student_class', '')
        category = request.form.get('category', '')
        content = request.form.get('content', '').strip()

        saved_image_path = None
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filename = f"user_{session['user_id']}_{int(datetime.utcnow().timestamp())}_{filename}"
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                saved_image_path = file_path

        if not content and saved_image_path:
            content = "[Bu not bir fotoğraf yüklemesi olarak kaydedildi. Yapay zeka analizi için 'Özetle' butonuna bas.]"

        if not content:
            content = ""

        new_note = Note(
            title=title,
            content=content,
            student_class=student_class,
            category=category,
            image_path=saved_image_path,
            user_id=session['user_id']
        )
        db.session.add(new_note)
        db.session.commit()
        flash('Not başarıyla eklendi!', 'success')
        return redirect(url_for('dashboard'))

    search = request.args.get('search', '').strip()
    filter_class = request.args.get('filter_class', '')
    filter_category = request.args.get('filter_category', '')

    query = Note.query.filter_by(user_id=session['user_id'])
    if search:
        query = query.filter(Note.title.ilike(f'%{search}%'))
    if filter_class:
        query = query.filter_by(student_class=filter_class)
    if filter_category:
        query = query.filter_by(category=filter_category)

    user_notes = query.order_by(Note.created_at.desc()).all()
    total_notes = Note.query.filter_by(user_id=session['user_id']).count()
    summarized = Note.query.filter_by(user_id=session['user_id']).filter(Note.summary.isnot(None)).count()

    return render_template('dashboard.html',
                           notes=user_notes,
                           total_notes=total_notes,
                           summarized=summarized,
                           search=search,
                           filter_class=filter_class,
                           filter_category=filter_category)


@app.route('/summarize/<int:note_id>')
def summarize_note(note_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    note = Note.query.get_or_404(note_id)

    if note.user_id != session['user_id']:
        flash('Yetkisiz erişim!', 'danger')
        return redirect(url_for('dashboard'))

    try:
        client = genai.Client()

        if note.image_path and os.path.exists(note.image_path):
            img = Image.open(note.image_path)
            prompt = (
                f"Sana bir {note.student_class} düzeyi {note.category} dersi notunun fotoğrafını gönderiyorum. "
                f"Lütfen bu fotoğraftaki tüm yazıları oku, ardından bir öğrencinin sınavdan önce çalışabileceği "
                f"şekilde önemli yerleri madde madde Türkçe özetle."
            )
            contents_list = [img, prompt]
        else:
            prompt = (
                f"Aşağıdaki {note.student_class} düzeyi {note.category} ders notunu bir öğrencinin sınavdan önce "
                f"hızlıca çalışabileceği şekilde, önemli noktaları vurgulayarak madde madde Türkçe özetle:\n\n{note.content}"
            )
            contents_list = [prompt]

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=contents_list,
        )

        note.summary = response.text
        db.session.commit()
        flash('Yapay zeka analizi tamamlandı! ✨', 'success')

    except Exception as e:
        flash(f'Yapay zeka hatası: {str(e)}', 'danger')

    return redirect(url_for('dashboard'))


@app.route('/delete/<int:note_id>', methods=['POST'])
def delete_note(note_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    note = Note.query.get_or_404(note_id)
    if note.user_id != session['user_id']:
        flash('Yetkisiz erişim!', 'danger')
        return redirect(url_for('dashboard'))

    if note.image_path and os.path.exists(note.image_path):
        os.remove(note.image_path)

    db.session.delete(note)
    db.session.commit()
    flash('Not silindi.', 'info')
    return redirect(url_for('dashboard'))


@app.route('/logout')
def logout():
    session.clear()
    flash('Güvenli çıkış yapıldı.', 'info')
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
