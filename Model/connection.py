import pandas as pd
import mysql.connector
import os
import numpy as np
import logging

def get_db_connection():
    connection = mysql.connector.connect(
        host='localhost',
        user='root',
        database='ocr2'
    )
    cursor = connection.cursor()
    return connection, cursor

def close_db_connection(connection, cursor):
    cursor.close()
    connection.close()

def process_file(file_path, file_content, file_type, num_pages, user_id):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    connection, cursor = get_db_connection()
    
    logging.info(f"Processing file: {file_path} for user ID: {user_id}")

    # Insert file metadata into the Files table
    file_metadata = {
        'user_id': user_id,  # Use the correct user_id
        'filename': os.path.basename(file_path),
        'file_size': os.path.getsize(file_path),
        'file_type': file_type,
        'num_pages': num_pages,
        'format_image': None,
        'content': file_content
    }

    insert_file_sql = """
        INSERT INTO Files (user_id, filename, file_size, file_type, num_pages, format_image, content)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """

    cursor.execute(insert_file_sql, (
        file_metadata['user_id'],
        file_metadata['filename'],
        file_metadata['file_size'],
        file_metadata['file_type'],
        file_metadata['num_pages'],
        file_metadata['format_image'],
        file_metadata['content']
    ))

    # Get the file_id of the inserted file
    file_id = cursor.lastrowid
    logging.info(f"File metadata inserted with file_id: {file_id} for user ID: {user_id}")

    # Read the Excel file
    df_table_structuree = pd.read_excel(file_path, sheet_name='Table Structurée')
    df_resultats_facture = pd.read_excel(file_path, sheet_name='Résultats Facture')

    # Replace NaN values with empty strings
    df_table_structuree = df_table_structuree.replace(np.nan, '', regex=True)
    df_resultats_facture = df_resultats_facture.replace(np.nan, '', regex=True)

    # Initialize a dictionary to hold the invoice data
    invoice_data = {
        'Date': '',
        'Numéro de facture': '',
        'Code ICE': '',
        'N de facture': '',
        'Montants écrits en lettres': '',
        'Adresse e-mail': '',
        'Numéro de téléphone': '',
        'Numéro de fax': ''
    }

    # Collect data for the Invoices table
    for index, row in df_resultats_facture.iterrows():
        if row['Champ'] in invoice_data:
            invoice_data[row['Champ']] = row['Valeur']

    # Insert data into the Invoices table
    sql = """
        INSERT INTO Invoices (file_id, n_de_facture, adresse_email, numero_telephone, numero_fax, date, code_ice, montants_ecrits_en_lettres)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    cursor.execute(sql, (
        file_id,
        invoice_data['N de facture'],
        invoice_data['Adresse e-mail'],
        invoice_data['Numéro de téléphone'],
        invoice_data['Numéro de fax'],
        invoice_data['Date'],
        invoice_data['Code ICE'],
        invoice_data['Montants écrits en lettres']
    ))
    logging.info(f"Invoice data inserted for file_id: {file_id}")

    # Check for actual column names before inserting into ExtractedData
    if 'Référence' in df_table_structuree.columns and 'Designation' in df_table_structuree.columns:
        # Insert data into the ExtractedData table for Hegimar
        for index, row in df_table_structuree.iterrows():
            sql = "INSERT INTO ExtractedData (file_id, field_name, field_value) VALUES (%s, %s, %s)"
            cursor.execute(sql, (file_id, 'Référence', row['Référence']))
            cursor.execute(sql, (file_id, 'Designation', row['Designation']))
            cursor.execute(sql, (file_id, 'Qte', row['Qte']))
            cursor.execute(sql, (file_id, 'Px unitaire', row['Px unitaire']))
            cursor.execute(sql, (file_id, 'Remise', row['Remise']))
            cursor.execute(sql, (file_id, 'Montant HT', row['Montant HT']))
            cursor.execute(sql, (file_id, 'NBL', row['NBL']))
        logging.info(f"Extracted data inserted for Hegimar with file_id: {file_id}")
    elif 'Référence' in df_table_structuree.columns:
        # Insert data into the ExtractedData table for Disway
        for index, row in df_table_structuree.iterrows():
            sql = "INSERT INTO ExtractedData (file_id, field_name, field_value) VALUES (%s, %s, %s)"
            cursor.execute(sql, (file_id, 'Référence', row['Référence']))
            cursor.execute(sql, (file_id, 'Désignation', row['Désignation']))
            cursor.execute(sql, (file_id, 'Qte', row['Qte']))
            cursor.execute(sql, (file_id, 'Px unitaire', row['Px unitaire']))
            cursor.execute(sql, (file_id, 'Remise', row['Remise']))
            cursor.execute(sql, (file_id, 'Montant HT', row['Montant HT']))
        logging.info(f"Extracted data inserted for Disway with file_id: {file_id}")
    else:
        # Insert data into the ExtractedData table for Boitaloc
        for index, row in df_table_structuree.iterrows():
            sql = "INSERT INTO ExtractedData (file_id, field_name, field_value) VALUES (%s, %s, %s)"
            cursor.execute(sql, (file_id, 'DESIGNATION', row['DESIGNATION']))
            cursor.execute(sql, (file_id, 'QTE', row['QTE']))
            cursor.execute(sql, (file_id, 'P.U H.T', row['P.U H.T']))
            cursor.execute(sql, (file_id, 'P.T H.T', row['P.T H.T']))
        logging.info(f"Extracted data inserted for Boitaloc with file_id: {file_id}")

    # Commit the transaction
    connection.commit()
    logging.info(f"Transaction committed for file: {file_path}")

    # Close the cursor and connection
    close_db_connection(connection, cursor)
    logging.info(f"File {os.path.basename(file_path)} processed and stored successfully.")

    return file_id

