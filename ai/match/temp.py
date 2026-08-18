import os
import kss
import requests
import json
from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_core.documents import Document
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
from google import genai
from google.genai import types
from chatbot import generate_answer_v3

data_path = '../../data/demo/demands.json'

with open(data_path, 'r', encoding='utf-8') as f:
    data = json.load(f)
    
def generate_db2(docs:json):
    #splitted_sentences = kss.split_sentences(text_documents)
    #joined_sentences = '\n'.join(splitted_sentences)
    
    model_name = 'BAAI/bge-m3'

    model_kwargs = {'device':'cuda'}
    encode_kwargs = {'normalize_embeddings':True}

    embeddings = HuggingFaceEmbeddings(
        model_name = model_name,
        model_kwargs = model_kwargs,
        encode_kwargs = encode_kwargs
    )
    
    '''text_splitter = RecursiveCharacterTextSplitter(
    separators=["\n"],
    chunk_size=400,    
    chunk_overlap=20,    
    length_function=len
    )'''
    
    #chunks = text_splitter.split_text(joined_sentences)
    
    documents = [
        Document(
            page_content = doc['demand_description'],
            metadata={
                "demand_id":doc['demand_id'],
                "company_name":doc['company_name'],
                "demand_description":doc['demand_description'],
                "required_quantity":doc['required_quantity'],
                "location":doc['location']
            }
        ) for doc in docs
    ]
    
    vector_db = Chroma(
    collection_name = 'my_documents',
    embedding_function = embeddings,
    persist_directory = './chroma_db'
    )
    
    vector_db.add_documents(documents)
    
    return vector_db

def generate_answer_v3(query, vector_db: Chroma):
    results = vector_db.similarity_search_with_relevance_scores(
            query,
            k = 1
            )
    docs = [doc for doc,_ in results]
    scores = [score for _,score in results]
    
    #doc, score = results[0]
        
    context = '\n'.join([doc.page_content for doc in docs])
    client = genai.Client(
        api_key = os.getenv('GOOGLE_API_KEY')
    )
    
    response = client.models.generate_content(
        model = 'gemini-2.5-flash',
        contents = f"""
            [역할]
            너는 문서 기반 질의응답 AI다.
            [수행작업] 
            ###
            주어진 참고자료의 정보를 이용하여 질문에 직접 답한다.
            문장을 그대로 반복하지 말고 내용을 이해하기 쉽게 정리한다.
            문서에 정보가 없다면 모른다고 답한다.
            ###
                        
            [참고자료]
            {context}
                        
            [질문]
            {query}
                        
            [출력 규칙]
            ###
            질문에 대한 답변만 출력한다.
            질문과 관련없는 내용은 출력하지 않는다.
            답변은 반드시 제공된 [출력 형식]에 맞춰 번호를 매겨 작성한다.
            마크다운 헤더(#), 이모지, 이모티콘 등 불필요한 특수문자는 사용하지 않는다.
            ###
                        
            [출력 형식]
            ###
            회사: A
            물품: X
            수량: 5
            거리: 13
            ###
        """,
        config = types.GenerateContentConfig(
            temperature = 0.2,
            top_k = 2,
            max_output_tokens = 2048,
            response_mime_type = 'application/json'
        )
    )
    return response.candidates[0].content.parts[0].text, max(scores), docs[0].metadata

def similarity_search(db:Chroma, query, k):
    results = db._similarity_search_with_relevance_scores(query, k)
    
    docs  = [doc for doc, _ in results]
    scores = [round(score,3) for _, score in results]
    
    return docs, scores

def rule_check(docs, passport:dict):
    total_report = []
    
    for doc in docs:
        report = {}
        meta = doc.metadata
        
        report['demand_id'] = meta['demand_id']
        report['company_name'] = meta['company_name']
        report['demand_description'] = meta['demand_description']

        
        
        #quantity_report = f"Passport: {passport['quantity']['value']} Demand: {meta['quantity_min']} ~ {meta['quantity_max']}"
        #report.append(quantity_report)
        
        if passport.get('quantity') is None:
            quantity_check = "null"
        elif passport['quantity'] >= meta.get('required_quantity', 0):
            quantity_check = "pass"
        else:
            quantity_check = "fail"
        
        if meta.get('location'):
            location_check = "pass"
        else:
            location_check = "fail"
            
        report["rule_check"] = {
            "quantity": quantity_check,
            "location": location_check
        }
        
        total_report.append(report)
        
        '''condition_report = f"Passport condition: {passport['condition']}"
        report.append(condition_report)
        
        if any(condition in passport['condition'] for condition in meta['accepted_conditions']):
            report.append('Pass')
        else:
            report.append('Fail')
            
        description = " ".join(report)
        total_report.append(description)'''
    
    json_report = json.dumps(total_report, ensure_ascii= False, indent=2)
    return json_report
    
      

if __name__ == '__main__':
    load_dotenv()
    #query = "연마 공정에서 발생한 실리카가 포함된 공정 부산물"
    data_db = generate_db2(data)
    
    with open('../../data/demo/passport.json', 'r', encoding='utf-8') as f:
        passport = json.load(f)
   
    desc = passport[0].get('description') or ''
    cond = passport[0].get('condition') or ''
    comp = passport[0].get('composition') or ''
    
    query = ", ".join([d for d in [desc, cond, comp] if d])  
    
    docs, scores = similarity_search(data_db, query, 1)
    
    report = rule_check(docs, passport[0])
    print(report)
    ####
    #print([(doc.page_content, doc.metadata, score) for doc,score in zip(docs,scores)])
    #print(type(docs))
    
    
   