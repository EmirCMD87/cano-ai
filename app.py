import os
from flask import Flask, render_template, redirect, url_for, request, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from google import genai
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'cano_gizli_123')
# Render için kalıcı Linux klasör yolu (.db sıfırlanmaz)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/platform.db'
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
    questions = db.Column(db.Text, nullable=True) # AI Sınav Soruları Alanı
    image_path = db.Column(db.String(200), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

with app.app_context():
    db.create_all()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if User.query.filter_by(username=username).first():
            flash('Kullanıcı adı alınmış!', 'danger')
            return redirect(url_for('register'))
        new_user = User(username=username, password=generate_password_hash(password, method='scrypt'))
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            session['user_id'] = user.id
            session['username'] = user.username
            return redirect(url_for('dashboard'))
        flash('Hata! Kullanıcı adı veya şifre yanlış.', 'danger')
    return render_template('login.html')

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user_id' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        title = request.form.get('title')
        student_class = request.form.get('student_class')
        category = request.form.get('category')
        content = request.form.get('content', '')
        image_path = None
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                filename = secure_filename(f"user_{session['user_id']}_{file.filename}")
                path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(path)
                image_path = path
        new_note = Note(title=title, content=content, student_class=student_class, category=category, image_path=image_path, user_id=session['user_id'])
        db.session.add(new_note)
        db.session.commit()
        return redirect(url_for('dashboard'))
    user_notes = Note.query.filter_by(user_id=session['user_id']).all()
    return render_template('dashboard.html', notes=user_notes)

@app.route('/summarize/<int:note_id>')
def summarize_note(note_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    note = Note.query.get_or_404(note_id)
    try:
        client = genai.Client()
        # Adaptif Eğitim Promptu
        instruction = f"""
        Sen 9. sınıf öğrencilerine ders anlatan uzman, samimi ve vizyoner bir lise öğretmenisin. 
        Öncelikle sana verilen bu {note.student_class} seviyesindeki {note.category} ders notunu çok derinlemesine analiz et.
        
        Senden iki ana bölümden oluşan bir içerik üretmeni istiyorum. Bölüm başlıklarını AYNEN aşağıdaki gibi yazmalısın:

        1. BÖLÜM BAŞLIĞI: 📝 YAPAY ZEKA DERS ÖZETİ
        Bu başlık altında konunun temel mantığını, can alıcı püf noktalarını ve sınavda kesin çıkacak yerleri geniş, detaylı ve son derece açıklayıcı maddeler halinde anlat. Kısa kesme, rehberlik et.

        2. BÖLÜM BAŞLIĞI: 🧠 BİLGİ ÖLÇME VE HEDEF TESTİ
        Bu başlık altında, öğrencinin konuyu ne kadar anladığını ölçmek için tam 3 adet çoktan seçmeli (A, B, C, D şıklı) kaliteli soru hazırla. Soruların hemen altına doğru cevapları ve kısa çözümlerini de ekle ki öğrenci kendi teşhisini koyabilsin.
        """
        
        if note.image_path:
            response = client.models.generate_content(model='gemini-2.0-flash', contents=[Image.open(note.image_path), instruction])
        else:
            response = client.models.generate_content(model='gemini-2.0-flash', contents=[note.content, instruction])
        
        full_text = response.text
        
        # Metni akıllıca ikiye bölüp veritabanına kaydedelim
        if "🧠 BİLGİ ÖLÇME VE HEDEF TESTİ" in full_text:
            parts = full_text.split("🧠 BİLGİ ÖLÇME VE HEDEF TESTİ")
            note.summary = parts[0].replace("📝 YAPAY ZEKA DERS ÖZETİ", "").strip()
            note.questions = parts[1].strip()
        else:
            note.summary = full_text
            note.questions = "Bu not için test soruları oluşturulurken bir hata oluştu. Lütfen tekrar deneyin."
            
        db.session.commit()
        flash('Analiz başarıyla tamamlandı, test hazır!', 'success')
    except Exception as e:
        flash(f'Hata: {str(e)}', 'danger')
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
