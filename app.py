import os
from flask import Flask, render_template, redirect, url_for, request, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from google import genai
from PIL import Image
# GİZLİ AYAR DOSYASI İÇİN KÜTÜPHANEYİ EKLEDİK
from dotenv import load_dotenv

# .env dosyasındaki API anahtarını bilgisayarın hafızasına otomatik yükler
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'cano_ders_platformu_super_gizli_anahtar_123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///platform.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    notes = db.relationship('Note', backref='author', lazy=True)

class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    student_class = db.Column(db.String(20), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    content = db.Column(db.Text, nullable=False)
    summary = db.Column(db.Text, nullable=True)
    image_path = db.Column(db.String(200), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

with app.app_context():
    db.create_all()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# --- ROTALAR (ROUTES) ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user_exists = User.query.filter_by(username=username).first()
        if user_exists:
            flash('Bu kullanıcı adı zaten alınmış!', 'danger')
            return redirect(url_for('register'))
            
        hashed_password = generate_password_hash(password, method='scrypt')
        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        
        flash('Başarıyla kayıt oldun! Giriş yapabilirsin.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['username'] = user.username
            flash('Başarıyla giriş yapıldı!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Kullanıcı adı veya şifre hatalı!', 'danger')
    return render_template('login.html')

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        title = request.form.get('title')
        student_class = request.form.get('student_class')
        category = request.form.get('category')
        content = request.form.get('content', '')
        
        saved_image_path = None
        
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filename = f"user_{session['user_id']}_{filename}"
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                saved_image_path = file_path

        if not content and saved_image_path:
            content = "[Bu not bir fotoğraf yüklemesi olarak kaydedildi. İçeriği analiz etmek için aşağıdaki butona basın.]"

        new_note = Note(title=title, content=content, student_class=student_class, category=category, image_path=saved_image_path, user_id=session['user_id'])
        db.session.add(new_note)
        db.session.commit()
        flash('Not başarıyla eklendi!', 'success')
        return redirect(url_for('dashboard'))
        
    user_notes = Note.query.filter_by(user_id=session['user_id']).all()
    return render_template('dashboard.html', notes=user_notes)

@app.route('/summarize/<int:note_id>')
def summarize_note(note_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    note = Note.query.get_or_404(note_id)
    
    if note.user_id != session['user_id']:
        flash('Yetkisiz erişim!', 'danger')
        return redirect(url_for('dashboard'))
        
    try:
        # load_dotenv sayesinde client() burayı artık otomatik okuyor
        client = genai.Client()
        
        if note.image_path and os.path.exists(note.image_path):
            img = Image.open(note.image_path)
            prompt = f"Sana bir {note.student_class} düzeyi {note.category} dersi notunun fotoğrafını gönderiyorum. Lütfen bu fotoğraftaki tüm yazıları oku, ardından bir öğrencinin sınavdan önce çalışabileceği şekilde önemli yerleri madde madde Türkçe özetle."
            contents_list = [img, prompt]
        else:
            prompt = f"Aşağıdaki {note.student_class} düzeyi {note.category} ders notunu bir öğrencinin sınavdan önce hızlıca çalışabileceği şekilde, önemli noktaları vurgulayarak madde madde Türkçe özetle:\n\n{note.content}"
            contents_list = [prompt]
            
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=contents_list,
        )
        
        note.summary = response.text
        db.session.commit()
        flash('Yapay zeka analizi ve özeti başarıyla tamamlandı!', 'success')
        
    except Exception as e:
        flash(f'Yapay zeka hatası: {str(e)}', 'danger')
        
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    flash('Güvenli çıkış yapıldı.', 'info')
    return redirect(url_for('index'))

if __name__ == '__main__':
    # host='0.0.0.0' sayesinde ngrok ve dış cihazlar artık bağlanabilir!
    app.run(debug=True, host='0.0.0.0', port=8080)
