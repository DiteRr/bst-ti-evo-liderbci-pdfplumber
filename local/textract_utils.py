import time
import boto3
import datetime

s3 = boto3.client('s3')
textract = boto3.client('textract', region_name='us-east-1')

def start_textract_job(bucket, key):
    response = textract.start_document_text_detection(
        DocumentLocation={'S3Object': {'Bucket': bucket, 'Name': key}}
    )
    return response['JobId']

def is_job_complete(job_id):
    response = textract.get_document_text_detection(JobId=job_id)
    return response['JobStatus'], response

def get_job_results(job_id):
    pages = {}
    next_token = None
    while True:
        if next_token:
            response = textract.get_document_text_detection(JobId=job_id, NextToken=next_token)
        else:
            response = textract.get_document_text_detection(JobId=job_id)

        for block in response['Blocks']:
            if block['BlockType'] == 'LINE':
                page_num = block['Page']
                pages.setdefault(page_num, []).append(block['Text'])

        next_token = response.get('NextToken')
        if not next_token:
            break
    return pages

def mover_a_lotes(bucket, key):
    fecha = datetime.datetime.now().strftime("%Y-%m-%d")
    nuevo_key = key.replace("INGRESO/", f"LOTES/{fecha}/")
    s3.copy_object(Bucket=bucket, CopySource={"Bucket": bucket, "Key": key}, Key=nuevo_key)
    s3.delete_object(Bucket=bucket, Key=key)
    lote = nuevo_key.split("/")[1]
    print(f"Archivo movido: {key} → {nuevo_key}, Lote: {lote}")
    return nuevo_key, lote
