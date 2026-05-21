from flask_sqlalchemy import SQLAlchemy

# Veritabanı nesnemizi tanımlıyoruz, app.py içinde bunu bağlayacağız
db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)  # Şifreleri hash'leyerek saklayacağız
    role = db.Column(db.String(20), default='student')    # 'student' veya 'teacher'
    
    # Kullanıcının yüklediği notlarla olan ilişkisi (1 kullanıcının çokça notu olabilir)
    notes = db.relationship('Note', backref='author', lazy=True)

class Note(db.Model):
    __tablename__ = 'notes'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)      # Notun başlığı (Örn: Fizik 1. Dönem)
    content = db.Column(db.Text, nullable=True)            # Notun metin içeriği
    category = db.Column(db.String(50), nullable=False)    # Matematik, Fizik, Kimya vb.
    file_path = db.Column(db.String(200), nullable=True)   # Eğer PDF/Word yüklenirse dosya yolu
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    # Notu hangi kullanıcının yüklediğini tutan foreign key
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)