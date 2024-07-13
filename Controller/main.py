# l'ajout d'envoyer en mail quand on oublie le mdp 
import sys 
import os
import re
import pandas as pd
import pytesseract
sys.path.insert(1, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'Model')))
import cv2
from PIL import Image
from pdf2image import convert_from_path
from regex_patterns import extract_total_words_and_amounts, extract_table_data, extract_date, extract_invoice_number, extract_ice_code, extract_totals
from fastapi import FastAPI, File, UploadFile, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from passlib.context import CryptContext
from connection import process_file as db_process_file, get_db_connection, close_db_connection
import logging
import bcrypt

from fastapi_mail import FastMail, MessageSchema, ConnectionConfig

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Configuration de la journalisation
logging.basicConfig(level=logging.INFO)

# Setup sécurité
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

app = FastAPI()

from fastapi.staticfiles import StaticFiles

# Ajoutez cette ligne pour monter le répertoire assets
app.mount("/assets", StaticFiles(directory="assets"), name="assets")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

global_user_id = None

def verify_password(plain_password, hashed_password):
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except AttributeError as e:
        logging.error(f"Error verifying password: {str(e)}")
        return False

def get_password_hash(password):
    return pwd_context.hash(password)

def authenticate_user(email: str, password: str):
    logging.info(f"Authenticating user with email: {email}")
    connection, cursor = get_db_connection()
    cursor.execute("SELECT id, password FROM users WHERE email = %s", (email,))
    user = cursor.fetchone()
    close_db_connection(connection, cursor)
    if user:
        logging.info(f"User found: {user[0]}")
        if verify_password(password, user[1]):
            logging.info("Password verification succeeded")
            return user[0]
        else:
            logging.info("Password verification failed")
    else:
        logging.info("User not found")
    return False

@app.get("/home", response_class=HTMLResponse)
def home_page():
    with open("View/home.html", "r") as file:
        return HTMLResponse(content=file.read(), status_code=200)

@app.get("/about", response_class=HTMLResponse)
def about_page():
    with open("View/about.html", "r") as file:
        return HTMLResponse(content=file.read(), status_code=200)

@app.get("/contact", response_class=HTMLResponse)
def contact_page():
    with open("View/contact.html", "r") as file:
        return HTMLResponse(content=file.read(), status_code=200)
    
@app.get("/login", response_class=HTMLResponse)
def login_page():
    with open("View/login.html", "r") as file:
        return HTMLResponse(content=file.read(), status_code=200)



@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user_id = authenticate_user(form_data.username, form_data.password)
    if not user_id:
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    return {"access_token": user_id, "token_type": "bearer"}

def get_current_user(request: Request):
    user_id = request.cookies.get("reel_id")  # Utilisez reel_id au lieu de user_id
    logging.info(f"Retrieved reel_id from cookie: {user_id}")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return int(user_id)



def get_current_user(request: Request):
    user_id = request.cookies.get("user_id")
    if user_id is None:
        user_id = 1  # Temporarily fix the user_id to 1
    logging.info(f"Retrieved user_id from cookie: {user_id}")
    return int(user_id)

@app.get("/api/current_user")
async def get_current_user_api(request: Request):
    user_id = get_current_user(request)
    return JSONResponse(content={"user_id": user_id}, status_code=200)


@app.post("/api/login")
async def login_user(data: dict, response: Response):
    global global_user_id
    try:
        email = data.get("email")
        password = data.get("password")
        logging.info(f"Login attempt for email: {email}")
        user_id = authenticate_user(email, password)
        if not user_id:
            logging.info("Login failed: Incorrect email or password")
            return JSONResponse(content={"error": "Email ou mot de passe incorrect"}, status_code=400)
        
        logging.info(f"Login successful for user ID: {user_id}")
        
        # Stocker l'ID utilisateur dans une variable globale
        global_user_id = user_id

        # Assurez-vous que le cookie est défini correctement
        response.set_cookie(key="user_id", value=str(user_id), httponly=True, samesite='Lax')
        response.set_cookie(key="reel_id", value=str(user_id), samesite='Lax')  # Supprimez httponly pour rendre le cookie accessible en JS
        
        logging.info(f"Set cookie for user ID: {user_id}")
        logging.info(f"Set reel_id cookie for user ID: {user_id}")
        return RedirectResponse(url="/upload2", status_code=302)
    except Exception as e:
        logging.error(f"Error during login: {str(e)}")
        return JSONResponse(content={"error": "Une erreur inconnue est survenue."}, status_code=500)


@app.post("/api/logout")
async def logout_user(response: Response):
    logging.info("User logged out, cookie user_id deleted")
    response.delete_cookie("user_id")
    return RedirectResponse(url="/login")


@app.post("/api/register")
async def register_user(data: dict, response: Response):
    name = data.get("name")
    surname = data.get("surname")
    email = data.get("email")
    password = data.get("password")
    
    hashed_password = get_password_hash(password)
    
    connection, cursor = get_db_connection()
    cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
    existing_user = cursor.fetchone()
    
    if existing_user:
        close_db_connection(connection, cursor)
        return JSONResponse(content={"error": "L'adresse email est déjà utilisée"}, status_code=400)
    
    cursor.execute("""
        INSERT INTO users (name, surname, email, password)
        VALUES (%s, %s, %s, %s)
    """, (name, surname, email, hashed_password))
    connection.commit()
    cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
    user_id = cursor.fetchone()[0]
    close_db_connection(connection, cursor)
    
    response.set_cookie(key="user_id", value=str(user_id))
    
    return JSONResponse(content={"message": "Inscription réussie. Vous pouvez maintenant vous connecter."}, status_code=200)

@app.get("/login", response_class=HTMLResponse)
def login_page():
    with open("View/login.html", "r") as file:
        return HTMLResponse(content=file.read(), status_code=200)

@app.get("/register", response_class=HTMLResponse)
def register_page():
    with open("View/register.html", "r") as file:
        return HTMLResponse(content=file.read(), status_code=200)

@app.get("/", response_class=HTMLResponse)
def root_redirect():
    return RedirectResponse(url="/home")


@app.get("/upload2", response_class=HTMLResponse)
def upload2_page(request: Request):
    global global_user_id
    try:
        user_id = get_current_user(request)
        logging.info(f"Access to upload2 page with user ID: {user_id}")
        with open("View/upload2.html", "r") as file:
            content = file.read().replace("{{user_id}}", str(global_user_id))
            return HTMLResponse(content=content, status_code=200)
    except HTTPException:
        return RedirectResponse(url="/login")

@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    global global_user_id
    try:
        user_id = get_current_user(request)
        logging.info(f"Root access with user ID: {user_id}")
        with open("View/upload2.html", "r") as file:
            content = file.read().replace("{{user_id}}", str(global_user_id))
            return HTMLResponse(content=content, status_code=200)
    except HTTPException:
        return RedirectResponse(url="/login")


@app.get("/data_page/{file_id}", response_class=HTMLResponse)
def read_data_page(file_id: int, request: Request):
    user_id = get_current_user(request)
    with open("View/data_page.html", "r") as file:
        return HTMLResponse(content=file.read(), status_code=200)

@app.get("/last_files", response_class=HTMLResponse)
def read_last_files_page():
    with open("View/last_files.html", "r") as file:
        return HTMLResponse(content=file.read(), status_code=200)

@app.get("/api/last_files")
async def get_last_files(request: Request):
    global global_user_id
    logging.info(f"Fetching last files for user ID: {global_user_id}")  
    # Affichez l'ID de l'utilisateur dans la console
    connection, cursor = get_db_connection()
    try:
        cursor.execute("""
            SELECT id AS file_id, filename AS name, file_type AS type 
            FROM files 
            WHERE user_id = %s 
            ORDER BY upload_date DESC 
            LIMIT 10
        """, (global_user_id,))
        rows = cursor.fetchall()
        files = [{"file_id": row[0], "name": row[1], "type": row[2]} for row in rows]
    finally:
        close_db_connection(connection, cursor)
    return files



@app.post("/api/delete_file/{file_id}")
async def delete_file(file_id: int, request: Request):
    global global_user_id
    connection, cursor = get_db_connection()
    try:
        # Supprimer les entrées de la table ExtractedData liées au file_id
        cursor.execute("DELETE FROM ExtractedData WHERE file_id = %s", (file_id,))
        
        # Supprimer les entrées de la table Invoices liées au file_id
        cursor.execute("DELETE FROM Invoices WHERE file_id = %s", (file_id,))
        
        # Supprimer le fichier de la table files lié au file_id et à l'ID utilisateur
        cursor.execute("DELETE FROM files WHERE id = %s AND user_id = %s", (file_id, global_user_id))
        
        connection.commit()
        return {"message": "Fichier supprimé avec succès"}
    except Exception as e:
        connection.rollback()
        return {"error": str(e)}
    finally:
        close_db_connection(connection, cursor)


@app.get("/admin_home", response_class=HTMLResponse)
def admin_home_page(request: Request):
    global global_user_id
    if global_user_id != 1:
        logging.info(f"Access denied for user ID: {global_user_id}")
        raise HTTPException(status_code=403, detail="Access forbidden")
    
    logging.info(f"Admin home access with user ID: {global_user_id}")
    with open("View/admin_home.html", "r") as file:
        return HTMLResponse(content=file.read(), status_code=200)

    
@app.get("/admin_phpmyadmin", response_class=HTMLResponse)
def admin_phpmyadmin_page(request: Request):
    try:
        user_id = get_current_user(request)
        logging.info(f"Admin PHPMyAdmin access with user ID: {user_id}")
        with open("View/admin_phpmyadmin.html", "r") as file:
            return HTMLResponse(content=file.read(), status_code=200)
    except HTTPException:
        return RedirectResponse(url="/login")

@app.get("/admin_users", response_class=HTMLResponse)
def admin_users_page(request: Request):
    try:
        user_id = get_current_user(request)
        logging.info(f"Admin users access with user ID: {user_id}")
        with open("View/admin_users.html", "r") as file:
            return HTMLResponse(content=file.read(), status_code=200)
    except HTTPException:
        return RedirectResponse(url="/login")

@app.get("/api/admin_users")
async def get_admin_users():
    connection, cursor = get_db_connection()
    try:
        cursor.execute("SELECT id, name, surname, email FROM users")
        users = cursor.fetchall()
        users_data = {}
        for user in users:
            user_id = user[0]
            cursor.execute("SELECT id AS file_id, filename FROM files WHERE user_id = %s", (user_id,))
            files = cursor.fetchall()
            users_data[user_id] = {
                "info": {
                    "id": user_id,
                    "name": user[1],
                    "surname": user[2],
                    "email": user[3]
                },
                "files": [{"file_id": file[0], "filename": file[1]} for file in files]
            }
    finally:
        close_db_connection(connection, cursor)
    return JSONResponse(content=users_data)

@app.post("/api/delete_user/{user_id}")
async def delete_user(user_id: int):
    connection, cursor = get_db_connection()
    try:
        # Supprimer les entrées de la table ExtractedData liées à user_id
        cursor.execute("DELETE FROM ExtractedData WHERE file_id IN (SELECT id FROM files WHERE user_id = %s)", (user_id,))
        
        # Supprimer les entrées de la table Invoices liées à user_id
        cursor.execute("DELETE FROM Invoices WHERE file_id IN (SELECT id FROM files WHERE user_id = %s)", (user_id,))
        
        # Supprimer les fichiers liés à user_id
        cursor.execute("DELETE FROM files WHERE user_id = %s", (user_id,))
        
        # Supprimer l'utilisateur lui-même
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        
        connection.commit()
        return JSONResponse(content={"message": "Utilisateur et tous ses fichiers ont été supprimés avec succès."})
    except Exception as e:
        connection.rollback()
        return JSONResponse(content={"error": str(e)}, status_code=500)
    finally:
        close_db_connection(connection, cursor)


# main555.py

# Import required modules

#### mail thing 
# Configuration pour l'envoi des emails
conf = ConnectionConfig(
    MAIL_USERNAME="abdobouzine2003@gmail.com",
    MAIL_PASSWORD="ubuh stnv motn yrve",
    MAIL_FROM="abdobouzine2003@gmail.com",
    MAIL_PORT=587,
    MAIL_SERVER="smtp.gmail.com",
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True
)


@app.get("/forgot_password", response_class=HTMLResponse)
def forgot_password_page():
    with open("View/forgot_password.html", "r") as file:
        return HTMLResponse(content=file.read(), status_code=200)

@app.post("/api/reset_password")
async def reset_password(data: dict, response: Response):
    email = data.get("email")
    new_password = data.get("newPassword")

    if not email or not new_password:
        return JSONResponse(content={"error": "Email et mot de passe sont requis"}, status_code=400)

    connection, cursor = get_db_connection()
    cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
    user = cursor.fetchone()

    if not user:
        close_db_connection(connection, cursor)
        return JSONResponse(content={"error": "Email non trouvé"}, status_code=404)

    hashed_password = get_password_hash(new_password)
    cursor.execute("UPDATE users SET password = %s WHERE email = %s", (hashed_password, email))
    connection.commit()
    close_db_connection(connection, cursor)

    message = MessageSchema(
        subject="Réinitialisation de votre mot de passe",
        recipients=[email],
        body=f"Votre mot de passe a été réinitialisé. Votre nouveau mot de passe est : {new_password}",
        subtype="plain"
    )

    fm = FastMail(conf)
    await fm.send_message(message)

    return RedirectResponse(url="/login", status_code=302)

def extract_text_from_image(image_path):
    logging.debug(f"Extracting text from image: {image_path}")
    
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"File not found: {image_path}")

    image = Image.open(image_path)
    gray_image = cv2.cvtColor(cv2.imread(image_path), cv2.COLOR_BGR2GRAY)

    temp_gray_image_path = "temp2/graypic.jpg"
    os.makedirs(os.path.dirname(temp_gray_image_path), exist_ok=True)
    cv2.imwrite(temp_gray_image_path, gray_image)

    ocr_result = pytesseract.image_to_string(temp_gray_image_path)
    return ocr_result

def pdf_to_images(pdf_path, output_folder):
    images = convert_from_path(pdf_path)
    image_paths = []
    for i, image in enumerate(images):
        image_path = os.path.join(output_folder, f"page_{i+1}.jpg")
        image.save(image_path, 'JPEG')
        image_paths.append(image_path)
    return image_paths

def extraire_montants_lettres(texte):
    montants_lettres = []
    patterns = [
        re.compile(r"(?:Arr[eé]t[eé]e.*?somme de:)\s*(.*?)[\n|$]"),
        re.compile(r"(?:ARRETER LA PRESENTE FACTURE.*?somme de:)\s*(.*?)[\n|$]"),
        re.compile(r"(?:Arr[eé]ter la.*?somme de:)\s*(.*?)[\n|$]"),
        re.compile(r"Arr[eé]t[eé]e.*?somme de TTC : ss\s*(.*?)[\n|$]"),
        re.compile(r"Arr[eé]ter la.*?somme de.*?\d+\s*(.*?)[\n|$]"),
        re.compile(r"ARRETEE LA PRESENTE FACTURE A LA SOMME DE :\s*(.*?)[\n|$]"),
        re.compile(r"Arr[eé]ter la.*?facture.*?\d+a\s*somme de\s*(.*?)[\n|$]"),
        re.compile(r"Arr[eé]ter la.*?somme de.*?de\s*(.*?)[\n|$]")
    ]
    for pattern in patterns:
        matches = pattern.findall(texte)
        montants_lettres.extend(matches)
    return montants_lettres

def extraire_totaux(texte):
    pattern_totaux = re.compile(r"(?:(?:TOTALH\.T\.|T\.V\.A|Total)[^|]+\|\s*[\d\s.,-]+)")
    totaux_extraits = pattern_totaux.findall(texte)
    return totaux_extraits

def clean_and_structure_data(text, filename):
    structured_data = []
    lines = text.split('\n')
    logging.debug(f"Processing {len(lines)} lines for file: {filename}")

    if "BOITALOC" in filename:
        header = ["DESIGNATION", "QTE", "P.U H.T", "P.T H.T"]
        structured_data.append(header)
        for line in lines:
            match = re.match(r'(.*?)(\d+)\s+(\d{1,3},\d{2})\s+(\d{1,3},\d{2})$', line)
            if match:
                designation = match.group(1).strip()
                qte = match.group(2).strip()
                pu_ht = match.group(3).strip()
                pt_ht = match.group(4).strip()
                structured_data.append([designation, qte, pu_ht, pt_ht])

    elif "disway" in filename:
        header = ["Référence", "Désignation", "Qte", "Px unitaire", "Remise", "Montant HT"]
        structured_data.append(header)
        current_ref = ""
        current_designation = ""
        current_qte = ""
        current_pxunitaire = ""
        current_remise = ""
        current_montantht = ""
        designation_part = []
        capture_data = False
        for line in lines:
            line = line.strip()
            if line.startswith("SM-"):
                if current_ref:
                    structured_data.append([current_ref, ' '.join(designation_part).strip(), current_qte, current_pxunitaire, current_remise, current_montantht])
                parts = line.split()
                current_ref = parts[0]
                designation_part = parts[1:]
                current_qte = ""
                current_pxunitaire = ""
                current_remise = ""
                current_montantht = ""
                capture_data = False
            elif re.search(r'\d+\s+\d{1,3},\d{2}\s+\d{1,3},\d{2}\s+\d{1,3},\d{2}', line):
                capture_data = True
                parts = re.split(r'\s+', line)
                current_qte = parts[-4]
                current_pxunitaire = parts[-3]
                current_remise = parts[-2]
                current_montantht = parts[-1]
            elif capture_data:
                designation_part.append(line)
                if "CODE EAN" in line or "S/N" in line:
                    current_designation += " " + line
                else:
                    current_designation += " " + line
        if current_ref:
            structured_data.append([current_ref, ' '.join(designation_part).strip(), current_qte, current_pxunitaire, current_remise, current_montantht])

    elif "Hegimar" in filename:
        header = ["Référence", "Designation", "Qte", "Px unitaire", "Remise", "Montant HT", "NBL"]
        structured_data.append(header)
        current_item = {}
        for line in lines:
            match = re.match(r'(\w+)\s+(.+?)\s+(\d+,\d{2})\s+(\d{1,3},\d{2})\s+(\d+,\d{2})\s+(\d+,\d{2})$', line)
            if match:
                current_item = {
                    'Référence': match.group(1).strip(),
                    'Designation': match.group(2).strip(),
                    'Qte': match.group(3).strip(),
                    'Px unitaire': match.group(4).strip(),
                    'Remise': match.group(5).strip(),
                    'Montant HT': match.group(6).strip(),
                    'NBL': ''
                }
                structured_data.append(current_item)
            else:
                match_alt = re.match(r'(\w+)\s+(.+?)\s+(\d+,\d{2})\s+(\d{1,3},\d{2})\s+(\d{1,3},\d{2})', line)
                if match_alt:
                    current_item = {
                        'Référence': match_alt.group(1).strip(),
                        'Designation': match_alt.group(2).strip(),
                        'Qte': match_alt.group(3).strip(),
                        'Px unitaire': match_alt.group(4).strip(),
                        'Montant HT': match_alt.group(5).strip(),
                        'NBL': ''
                    }
                    structured_data.append(current_item)
    return structured_data

def save_to_excel(structured_data, results_data, pdf_path):
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    output_folder = "results"
    os.makedirs(output_folder, exist_ok=True)
    output_file_name = f"{output_folder}/{base_name}_results.xlsx"
    with pd.ExcelWriter(output_file_name) as writer:
        df_structured = pd.DataFrame(structured_data[1:], columns=structured_data[0])
        df_results = pd.DataFrame(results_data, columns=['Champ', 'Valeur'])
        df_structured.to_excel(writer, sheet_name="Table Structurée", index=False)
        df_results.to_excel(writer, sheet_name="Résultats Facture", index=False)
    return output_file_name

def process_excel(file: UploadFile):
    df = pd.read_excel(file.file)
    invoices_data = df[['n_de_facture', 'adresse_email', 'numero_telephone', 'numero_fax', 'date', 'code_ice', 'montants_ecrits_en_lettres']]
    extracted_data = df.drop(columns=['n_de_facture', 'adresse_email', 'numero_telephone', 'numero_fax', 'date', 'code_ice', 'montants_ecrits_en_lettres'])

    connection, cursor = get_db_connection()
    try:
        for _, row in invoices_data.iterrows():
            cursor.execute("""
                INSERT INTO Invoices (n_de_facture, adresse_email, numero_telephone, numero_fax, date, code_ice, montants_ecrits_en_lettres)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, tuple(row))
        
        for _, row in extracted_data.iterrows():
            cursor.execute("""
                INSERT INTO ExtractedData (field_name, field_value)
                VALUES (%s, %s)
            """, tuple(row))
        
        connection.commit()
    finally:
        close_db_connection(connection, cursor)

@app.post("/process_file/")
async def process_file_endpoint(request: Request, file: UploadFile = File(...)):
    global global_user_id
    logging.info(f"User ID (reel_id) for the current request: {global_user_id}")

    if file.filename.endswith('.xlsx') or file.filename.endswith('.xls'):
        try:
            process_excel(file)
            return JSONResponse(content={"message": "Excel file processed successfully"}, status_code=200)
        except Exception as e:
            logging.error(f"Error processing Excel file: {str(e)}")
            return JSONResponse(content={"error": str(e)}, status_code=500)

    output_folder = 'temp_images'
    os.makedirs(output_folder, exist_ok=True)
    file_location = f"{output_folder}/{file.filename}"
    with open(file_location, "wb+") as file_object:
        file_content = file.file.read()
        file_object.write(file_content)

    if file.filename.endswith(('.jpg', '.jpeg', '.png')):
        extracted_text = extract_text_from_image(file_location)
        structured_data = clean_and_structure_data(extracted_text, file.filename)
        num_pages = 1  # Single image file
    elif file.filename.endswith('.pdf'):
        image_paths = pdf_to_images(file_location, output_folder)
        extracted_text = ""
        for image_path in image_paths:
            try:
                text = extract_text_from_image(image_path)
                extracted_text += text + "\n"
            except Exception as e:
                logging.error(f"Error extracting text from image: {str(e)}")
                return JSONResponse(content={"error": str(e)}, status_code=500)
        structured_data = clean_and_structure_data(extracted_text, file.filename)
        num_pages = len(image_paths)  # Number of pages in the PDF

    montants_lettres_extraits = extraire_montants_lettres(extracted_text)
    totaux = extraire_totaux(extracted_text)
    date_extracted = extract_date(extracted_text)
    invoice_number_extracted = extract_invoice_number(extracted_text)
    ice_code_extracted = extract_ice_code(extracted_text)
    total_ttc, total_ht_tva, total_lettres, total_tva = extract_totals(extracted_text)
    N_facture = extract_invoice_number(extracted_text)
    email_regex = r'\b[A-Za-z0-9._%+-]+@[A-Za.z0-9.-]+\.[A-Z|a-z]{2,}\b'
    phone_regex = r'\b(?:\+?212|0)\s*[1-9](?:[\s.-]*\d{2}){4}\b'
    fax_regex = r'\b(?:\+?212|0)\s*[1-9](?:[\s.-]*\d{2}){4}\b'
    emails = re.findall(email_regex, extracted_text)
    phones = re.findall(phone_regex, extracted_text)
    faxs = re.findall(fax_regex, extracted_text)
    results_data = [
        ('Date', date_extracted),
        ('Numéro de facture', invoice_number_extracted),
        ('Code ICE', ice_code_extracted),
        ('N de facture', N_facture),
        ('Montants écrits en lettres', ', '.join(montants_lettres_extraits)),
        ('Adresse e-mail', ', '.join(emails)),
        ('Numéro de téléphone', ', '.join(phones)),
        ('Numéro de fax', ', '.join(faxs))
    ]
    output_file = save_to_excel(structured_data, results_data, file_location)
    
    try:
        file_id = db_process_file(output_file, file_content, file.filename.split('.')[-1], num_pages, global_user_id)  # Utilisez global_user_id ici
        logging.info(f"File {file.filename} processed and stored successfully in the database with ID {file_id} for user ID {global_user_id}.")
    except Exception as e:
        logging.error(f"Error storing file {file.filename} in the database: {str(e)}")
        return JSONResponse(content={"error": f"Error storing file in database: {str(e)}"}, status_code=500)
    
    return JSONResponse(content={"filename": output_file, "file_id": file_id, "download_link": f"/results/{os.path.basename(output_file)}"})



@app.get("/results/{filename}")
async def get_result_file(filename: str):
    file_path = os.path.join("results", filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, filename=filename)
    return JSONResponse(content={"error": "File not found"}, status_code=404)

@app.get("/get_file_data/{file_id}")
async def get_file_data(file_id: int):
    connection, cursor = get_db_connection()
    
    cursor.execute("SELECT * FROM Invoices WHERE file_id = %s", (file_id,))
    invoices_data = cursor.fetchall()
    invoices_columns = [desc[0] for desc in cursor.description]
    
    cursor.execute("SELECT * FROM ExtractedData WHERE file_id = %s", (file_id,))
    extracted_data = cursor.fetchall()
    extracted_columns = [desc[0] for desc in cursor.description]
    
    close_db_connection(connection, cursor)
    
    return {
        "invoices": {
            "columns": invoices_columns,
            "data": invoices_data
        },
        "extracted_data": {
            "columns": extracted_columns,
            "data": extracted_data
        }
    }

@app.post("/update_table/")
async def update_table(data: dict):
    file_id = data.get('file_id')
    table = data.get('table')
    updates = data.get('updates')

    logging.debug(f"Received update request for file_id: {file_id}, table: {table}")
    logging.debug(f"Updates: {updates}")

    if not file_id or not table or not updates:
        logging.error("Invalid data for update")
        return JSONResponse(content={"error": "Invalid data"}, status_code=400)

    connection, cursor = get_db_connection()

    try:
        if table == 'Invoices':
            update_query = """
                UPDATE Invoices SET n_de_facture = %s, adresse_email = %s, numero_telephone = %s, numero_fax = %s, date = %s, code_ice = %s, montants_ecrits_en_lettres = %s
                WHERE file_id = %s
            """
            cursor.execute(update_query, (
                updates['n_de_facture'],
                updates['adresse_email'],
                updates['numero_telephone'],
                updates['numero_fax'],
                updates['date'],
                updates['code_ice'],
                updates['montants_ecrits_en_lettres'],
                file_id
            ))

        elif table == 'ExtractedData':
            for update in updates:
                update_query = """
                    UPDATE ExtractedData SET field_value = %s
                    WHERE id = %s
                """
                logging.debug(f"Executing query with values: field_value={update['field_value']}, id={update['id']}")
                cursor.execute(update_query, (
                    update['field_value'],
                    update['id']
                ))

        connection.commit()
        logging.info(f"Update successful for file_id: {file_id}, table: {table}")
        
        output_file_name = save_updated_data_to_excel(file_id)
        logging.info(f"Updated data saved to Excel: {output_file_name}")
        
        return JSONResponse(content={"message": "Update successful", "filename": output_file_name}, status_code=200)
    except Exception as e:
        connection.rollback()
        logging.error(f"Error during update: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)
    finally:
        close_db_connection(connection, cursor)

@app.post("/generate_xlsx/")
async def generate_xlsx(data: dict):
    file_id = data.get('file_id')

    if not file_id:
        return JSONResponse(content={"error": "Invalid file ID"}, status_code=400)

    connection, cursor = get_db_connection()

    cursor.execute("SELECT * FROM Invoices WHERE file_id = %s", (file_id,))
    invoices_data = cursor.fetchall()
    invoices_columns = [desc[0] for desc in cursor.description]

    cursor.execute("SELECT * FROM ExtractedData WHERE file_id = %s", (file_id,))
    extracted_data = cursor.fetchall()
    extracted_columns = [desc[0] for desc in cursor.description]

    close_db_connection(connection, cursor)

    invoices_df = pd.DataFrame(invoices_data, columns=invoices_columns)
    invoices_df = invoices_df[['n_de_facture', 'adresse_email', 'numero_telephone', 'numero_fax', 'date', 'code_ice', 'montants_ecrits_en_lettres']]
    invoices_df.columns = ['N de facture', 'Adresse e-mail', 'Numéro de téléphone', 'Numéro de fax', 'Date', 'Code ICE', 'Montants écrits en lettres']

    extracted_df = pd.DataFrame(extracted_data, columns=extracted_columns)

    structured_data = []
    if 'Référence' in extracted_df['field_name'].values:
        current_item = {}
        for _, row in extracted_df.iterrows():
            field_name = row['field_name']
            field_value = row['field_value']
            if field_name == 'Référence':
                if current_item:
                    structured_data.append(current_item)
                    current_item = {}
                current_item['Référence'] = field_value
            elif field_name in ['DESIGNATION', 'Désignation', 'Designation']:
                if 'Designation' in current_item:
                    current_item['Designation'] += f" {field_value}"
                else:
                    current_item['Designation'] = field_value
            elif field_name in ['QTE', 'Qte']:
                current_item['Qte'] = field_value
            elif field_name in ['P.U H.T', 'Px unitaire']:
                current_item['Px unitaire'] = field_value
            elif field_name in ['P.T H.T', 'Montant HT']:
                current_item['Montant HT'] = field_value
            elif field_name == 'Remise':
                current_item['Remise'] = field_value
            elif field_name == 'NBL':
                current_item['NBL'] = field_value

        if current_item:
            structured_data.append(current_item)

        structured_df = pd.DataFrame(structured_data)

        expected_columns = ['Référence', 'Designation', 'Qte', 'Px unitaire', 'Remise', 'Montant HT', 'NBL']
        for column in expected_columns:
            if column not in structured_df.columns:
                structured_df[column] = ""

        structured_df = structured_df[expected_columns]
    else:
        structured_data = []
        for _, row in extracted_df.iterrows():
            field_name = row['field_name']
            field_value = row['field_value']
            if field_name in ['DESIGNATION', 'Désignation', 'Designation']:
                structured_data.append({
                    'DESIGNATION': field_value,
                    'QTE': '',
                    'P.U H.T': '',
                    'P.T H.T': ''
                })
            elif field_name in ['QTE', 'Qte']:
                structured_data[-1]['QTE'] = field_value
            elif field_name == 'P.U H.T':
                structured_data[-1]['P.U H.T'] = field_value
            elif field_name == 'P.T H.T':
                structured_data[-1]['P.T H.T'] = field_value

        structured_df = pd.DataFrame(structured_data)

        expected_columns = ['DESIGNATION', 'QTE', 'P.U H.T', 'P.T H.T']
        for column in expected_columns:
            if column not in structured_df.columns:
                structured_df[column] = ""

        structured_df = structured_df[expected_columns]

    output_file_name = f"results/file_{file_id}_updated.xlsx"
    os.makedirs(os.path.dirname(output_file_name), exist_ok=True)
    with pd.ExcelWriter(output_file_name) as writer:
        invoices_df.to_excel(writer, sheet_name="Invoices", index=False)
        structured_df.to_excel(writer, sheet_name="Extracted Data", index=False)

    return JSONResponse(content={"filename": output_file_name}, status_code=200)

def save_updated_data_to_excel(file_id):
    connection, cursor = get_db_connection()
    
    cursor.execute("SELECT * FROM Invoices WHERE file_id = %s", (file_id,))
    invoices_data = cursor.fetchall()
    invoices_columns = [desc[0] for desc in cursor.description]
    
    cursor.execute("SELECT * FROM ExtractedData WHERE file_id = %s", (file_id,))
    extracted_data = cursor.fetchall()
    extracted_columns = [desc[0] for desc in cursor.description]
    
    close_db_connection(connection, cursor)
    
    invoices_df = pd.DataFrame(invoices_data, columns=invoices_columns)
    invoices_df = invoices_df[['n_de_facture', 'adresse_email', 'numero_telephone', 'numero_fax', 'date', 'code_ice', 'montants_ecrits_en_lettres']]
    invoices_df.columns = ['N de facture', 'Adresse e-mail', 'Numéro de téléphone', 'Numéro de fax', 'Date', 'Code ICE', 'Montants écrits en lettres']
    
    extracted_df = pd.DataFrame(extracted_data, columns=extracted_columns)
    extracted_df = extracted_df.drop_duplicates(subset=['file_id', 'field_name'])  
    
    extracted_pivot_df = extracted_df.pivot(index='file_id', columns='field_name', values='field_value').reset_index(drop=True)
    
    logging.debug("Actual columns in extracted_pivot_df: %s", extracted_pivot_df.columns.tolist())
    
    expected_columns = ['Référence', 'Désignation', 'Qte', 'Px unitaire', 'Remise', 'Montant HT']
    if len(extracted_pivot_df.columns) == len(expected_columns):
        extracted_pivot_df.columns = expected_columns
    else:
        logging.error("Length mismatch: Expected columns length: %d, Actual columns length: %d", len(expected_columns), len(extracted_pivot_df.columns))
    
    output_file_name = f"results/file_{file_id}_updated.xlsx"
    os.makedirs(os.path.dirname(output_file_name), exist_ok=True)
    with pd.ExcelWriter(output_file_name) as writer:
        invoices_df.to_excel(writer, sheet_name="Invoices", index=False)
        extracted_pivot_df.to_excel(writer, sheet_name="Extracted Data", index=False)
    
    return output_file_name

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
