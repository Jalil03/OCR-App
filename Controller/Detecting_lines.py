import os
import imghdr
import cv2
import numpy as np
from pdf2image import convert_from_path
import pytesseract
import re
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from PIL import Image

# Spécifiez le chemin vers Tesseract OCR si ce n'est pas dans votre PATH
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

poppler_path = r"C:\Users\PC\Desktop\Projects\PFE\Release-24.02.0-0\poppler-24.02.0\Library\bin"

app = FastAPI()

def convert_to_images(file_path, output_folder):
    file_extension = os.path.splitext(file_path)[1].lower()

    if file_extension == '.pdf':
        images = convert_from_path(file_path, poppler_path=poppler_path)
        for i, image in enumerate(images):
            image_path = os.path.join(output_folder, f'image_{i+1}.png')
            image.save(image_path, 'PNG')
            print(f'Image saved: {image_path}')
            process_image(image_path)  
            # Appliquez le traitement à l'image convertie
    elif imghdr.what(file_path) is not None:
        print(f'The file {file_path} is already an image.')
        process_image(file_path)  # Appliquez le traitement à l'image existante
    else:
        print(f'The file {file_path} is not a supported image or PDF.')

def process_image(image_path):
    image = cv2.imread(image_path)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (1, 1), 0)
    cv2.imwrite(os.path.join("output_images", "blur.png"), blur)
    thresh = cv2.threshold(blur, 0 , 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    cv2.imwrite(os.path.join("output_images", "thresh.png"), thresh)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 13))
    dilate = cv2.dilate(thresh, kernel, iterations=4)
    cv2.imwrite(os.path.join("output_images", "dilate.png"), dilate)

    # Détection des lignes horizontales et verticales du tableau
    horizontal_lines = detect_lines(thresh, horizontal=True)
    vertical_lines = detect_lines(thresh, horizontal=False)

    # Dessiner les lignes horizontales et verticales détectées sur l'image
    draw_lines(image, horizontal_lines, color=(0, 0, 255))
    draw_lines(image, vertical_lines, color=(255, 0, 0))

    # Extraire le texte de chaque ligne
    row_text = ""
    for i in range(len(horizontal_lines) - 1):
        row_text += extract_row_text(image, horizontal_lines, i)
        row_text += "\n"  # Ajouter une nouvelle ligne entre chaque ligne

    # Remplacer plusieurs nouvelles lignes par une seule ligne vide
    row_text = re.sub(r'\n+', '\n\n', row_text)

    # Sauvegarder le résultat final avec les lignes détectées
    output_path = os.path.join('output_images', 'bbox.png')
    cv2.imwrite(output_path, image)

    # Sauvegarder les lignes horizontales détectées dans une image séparée
    horizontal_lines_path = os.path.join('output_images', 'horizontal_lines.png')
    draw_lines_image(horizontal_lines, image.shape, 'output_images', 'horizontal_lines.png')

    # Sauvegarder les lignes verticales détectées dans une image séparée
    draw_lines_image(vertical_lines, image.shape, 'output_images', 'vertical_lines.png')

    print(f'Image processed: {image_path}')
    print_extracted_text(row_text)

    date_extracted = extract_date(row_text)
    invoice_number_extracted = extract_invoice_number(row_text)
    ice_code_extracted = extract_ice_code(row_text)
    totals = extract_totals(row_text)
    N_facture = extract_invoice_number(row_text)

    # Imprimer les résultats
    print("Date:", date_extracted)
    print("Invoice Number:", invoice_number_extracted)
    print("ICE Code:", ice_code_extracted)
    print("Totals:", totals)
    print("Invoice Number:", N_facture)

    # Ouvrir l'image traitée
    img = Image.open(output_path)
    img.show()


def detect_lines(image, horizontal=True):
    height, width = image.shape[:2]

    if horizontal:
        # Détecter les lignes horizontales
        lines = cv2.HoughLinesP(image, 1, np.pi/180, threshold=200, minLineLength=500, maxLineGap=5)
    else:
        # Détecter les lignes verticales
        lines = cv2.HoughLinesP(image, 1, np.pi/180, threshold=200, minLineLength=875, maxLineGap=5)

    detected_lines = []
    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line[0]
            detected_lines.append((x1, y1, x2, y2))
    return detected_lines

def draw_lines(image, lines, color):
    for line in lines:
        x1, y1, x2, y2 = line
        cv2.line(image, (x1, y1), (x2, y2), color, 2)

def draw_lines_image(lines, image_shape, output_folder, output_filename):
    image = np.zeros(image_shape, dtype=np.uint8)
    draw_lines(image, lines, color=(255, 255, 255))
    output_path = os.path.join(output_folder, output_filename)
    cv2.imwrite(output_path, image)


def extract_row_text(image, horizontal_lines, row_index):
    # Tri des lignes horizontales par coordonnée y
    horizontal_lines.sort(key=lambda y: y[1])

    # Récupération des coordonnées y de la ligne actuelle
    row_y1 = horizontal_lines[row_index][1]
    row_y2 = horizontal_lines[row_index + 1][1]

    # Extraction de la zone de la ligne actuelle
    row_region = image[row_y1:row_y2, :]

    # Vérifier si la région extraite contient du texte
    if np.any(row_region):
        # Conversion de l'image en texte à l'aide de Tesseract OCR
        row_text = pytesseract.image_to_string(row_region)
        # Diviser le texte sur les retours à la ligne
        row_text_lines = row_text.splitlines()
        # Filtrer les lignes vides et remplacer les retours à la ligne inattendus par des espaces
        row_text_lines = [line.strip() for line in row_text_lines if line.strip()]
        # Ajouter une ligne vide avant le texte de chaque ligne sauf la première
        if row_index != 0:
            row_text_lines.insert(0, "")
        # Rejoindre les lignes en un seul texte avec des retours à la ligne
        row_text = '\n'.join(row_text_lines)
    else:
        row_text = "No text found in this row"

    return row_text


def extract_date(text):
    regex_date = r'\b(\d{1,2}/\d{1,2}/\d{2,4})\b'  # Modifié pour inclure des années à 2 ou 4 chiffres
    date_match = re.search(regex_date, text)
    if date_match:
        return date_match.group(1)
    return None



def extract_invoice_number(text):
    # Expression régulière pour rechercher les numéros de facture
    regex_facture = r'FACTURE\s*N°\s*:\s*(F\d+)'
    
    # Recherche des correspondances pour le numéro de facture
    match_facture = re.search(regex_facture, text)
    
    # Si un numéro de facture est trouvé, le retourner
    if match_facture:
        return match_facture.group(1)
    
    # Si aucun numéro de facture n'est trouvé selon la première logique,
    # essayer de rechercher selon la deuxième logique
    regex_new = r'FACTUREN[°N]?\s*(\d+)\s*/\s*(\d+)'
    invoice_match = re.search(regex_new, text, re.IGNORECASE)
    
    # Renvoyer le numéro de facture si trouvé selon la nouvelle logique
    if invoice_match:
        return invoice_match.group(1)
    
    # Si aucun numéro de facture n'est trouvé, rechercher selon les lignes
    lines = text.split("\n")
    for line in lines:
        if "Numéro" in line:
            parts = line.split(":")
            if len(parts) > 1:
                return parts[1].strip()
    return None

def extract_ice_code(text):
    # Expression régulière pour rechercher les codes ICE
    regex_ice = r'ICE\s*([0-9]+)'
    
    # Recherche des correspondances pour le code ICE
    match_ice = re.search(regex_ice, text)
    
    # Si un code ICE est trouvé, le retourner
    if match_ice:
        return match_ice.group(1)
    
    # Si aucun code ICE n'est trouvé selon la première logique,
    # essayer de rechercher selon la deuxième logique
    regex_new = r'ICE\s*:\s*(\d{3}\s*\d{3}\s*\d{3}\s*\d{3}\s*\d{3})'
    ice_match_new = re.search(regex_new, text)
    
    # Renvoyer le code ICE si trouvé selon la nouvelle logique
    if ice_match_new:
        return ice_match_new.group(1)
    
    # Si aucun code ICE n'est trouvé, rechercher selon les lignes
    lines = text.split("\n")
    for line in lines:
        if "ICE" in line:
            parts = line.split(":")
            if len(parts) > 1:
                return parts[1].strip()
    return None



def extract_totals(text):
    # Modèle d'expression régulière pour extraire le total en chiffres et le total TTC
    regex_total_chiffres = r'(?<=TotalHT ~~ )([\d\s,.]+)'  # Expression régulière ajustée pour le total en chiffres
    regex_total_ttc = r'TOTAL[^\n]*'

    # Recherche du total en chiffres
    match_total_chiffres = re.search(regex_total_chiffres, text)
    total_chiffres = match_total_chiffres.group(1).strip() if match_total_chiffres else None

    # Recherche du total TTC
    match_total_ttc = re.search(regex_total_ttc, text)
    total_ttc = match_total_ttc.group(0).strip() if match_total_ttc else None

    return total_chiffres, total_ttc

def print_extracted_text(text):
    print("Texte extrait:")
    print(text)

def extraire_montants_lettres(texte):
    # Liste pour stocker les montants extraits
    montants_lettres = []

    # Motifs regex pour trouver les montants écrits en lettres
    pattern_montant_lettre_1 = re.compile(r"(?:Arr[eé]t[eé]e.*?somme de:)\s*(.*?)[\n|$]")
    pattern_montant_lettre_2 = re.compile(r"(?:ARRETER LA PRESENTE FACTURE.*?somme de:)\s*(.*?)[\n|$]")
    pattern_montant_lettre_3 = re.compile(r"(?:Arr[eé]ter la.*?somme de:)\s*(.*?)[\n|$]")
    pattern_montant_lettre_4 = re.compile(r"Arr[eé]t[eé]e.*?somme de TTC : ss\s*(.*?)[\n|$]")
    pattern_montant_lettre_5 = re.compile(r"Arr[eé]ter la.*?somme de.*?\d+\s*(.*?)[\n|$]")
    pattern_montant_lettre_6 = re.compile(r"ARRETEE LA PRESENTE FACTURE A LA SOMME DE :\s*(.*?)[\n|$]")
    pattern_montant_lettre_7 = re.compile(r"Arr[eé]ter la.*?facture.*?\d+a\s*somme de\s*(.*?)[\n|$]")
    pattern_montant_lettre_8 = re.compile(r"Arr[eé]ter la.*?somme de.*?de\s*(.*?)[\n|$]")

    # Rechercher les montants dans le contenu du texte
    matches_montant_lettre_1 = pattern_montant_lettre_1.findall(texte)
    matches_montant_lettre_2 = pattern_montant_lettre_2.findall(texte)
    matches_montant_lettre_3 = pattern_montant_lettre_3.findall(texte)
    matches_montant_lettre_4 = pattern_montant_lettre_4.findall(texte)
    matches_montant_lettre_5 = pattern_montant_lettre_5.findall(texte)
    matches_montant_lettre_6 = pattern_montant_lettre_6.findall(texte)
    matches_montant_lettre_7 = pattern_montant_lettre_7.findall(texte)
    matches_montant_lettre_8 = pattern_montant_lettre_8.findall(texte)

    # Ajouter les montants extraits à la liste
    montants_lettres.extend(matches_montant_lettre_1)
    montants_lettres.extend(matches_montant_lettre_2)
    montants_lettres.extend(matches_montant_lettre_3)
    montants_lettres.extend(matches_montant_lettre_4)
    montants_lettres.extend(matches_montant_lettre_5)
    montants_lettres.extend(matches_montant_lettre_6)
    montants_lettres.extend(matches_montant_lettre_7)
    montants_lettres.extend(matches_montant_lettre_8)

    return montants_lettres

@app.post("/process_file/")
async def process_file(file: UploadFile = File(...)):
    file_location = f"files/{file.filename}"
    
    # Créer le répertoire "files" s'il n'existe pas
    os.makedirs(os.path.dirname(file_location), exist_ok=True)
    
    # Sauvegarder le fichier uploadé
    with open(file_location, "wb") as buffer:
        buffer.write(await file.read())
    
    # Traiter le fichier
    output_folder = 'output_images'
    os.makedirs(output_folder, exist_ok=True)
    
    convert_to_images(file_location, output_folder)
    
    # Résultat fictif pour la démonstration
    result = {
        "message": "File processed successfully",
        "file_id": "12345",  # Remplacez par l'ID de fichier réel si applicable
        "download_link_bbox": f"/download_image/bbox.png",  # Lien pour télécharger l'image traitée bbox.png
        "download_link_horizontal_lines": f"/download_image/horizontal_lines.png",  # Lien pour télécharger l'image horizontal_lines.png
        "image_path": os.path.join(output_folder, 'bbox.png')
    }
    
    return JSONResponse(content=result)

@app.get("/download_image/{file_name}")
async def download_image(file_name: str):
    file_path = f"output_images/{file_name}"
    return FileResponse(path=file_path, filename=file_name, media_type='image/png')


@app.get("/download_image/{file_name}")
async def download_image(file_name: str):
    file_path = f"output_images/bbox.png"
    return FileResponse(path=file_path, filename="bbox.png", media_type='image/png')

@app.get("/")
async def main():
    with open("View/test3.html") as f:
        return HTMLResponse(f.read())

@app.get("/api/current_user")
async def current_user():
    # Données utilisateur fictives
    return {"user_id": 1}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=3000)
