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

"""
model_id = 'Qwen/Qwen2.5-3B-Instruct'

generator = pipeline(
    'text-generation',
    model=model_id,
    device_map = 'auto',
    dtype = 'auto')

load_dotenv()

model_name = 'BAAI/bge-m3'

model_kwargs = {'device':'cuda'}
encode_kwargs = {'normalize_embeddings':True}

embeddings = HuggingFaceEmbeddings(
    model_name = model_name,
    model_kwargs = model_kwargs,
    encode_kwargs = encode_kwargs
)

text_splitter = RecursiveCharacterTextSplitter(
    separators=["\n"],
    chunk_size=400,    
    chunk_overlap=20,    
    length_function=len
)

vector_db = Chroma(
    collection_name = 'my_documents',
    embedding_function = embeddings,
    persist_directory = './chroma_db'
)
###
"""
long_text = """
인공지능 기술이 발전하면서 대규모 언어 모델(LLM)은 놀라운 문장 생성 능력을 보여주고 있습니다. 하지만 이러한 모델들은 학습된 시점 이후의 최신 정보를 알지 못하거나, 특정 기업의 내부 데이터와 같은 비공개 정보에는 접근할 수 없다는 치명적인 한계를 가지고 있습니다. 또한, 모델이 잘 모르는 내용을 그럴듯하게 지어내는 환각 현상(Hallucination)도 실무 도입을 가로막는 주요 원인 중 하나입니다.
이러한 문제를 해결하기 위해 등장한 기술이 바로 검색 증강 생성(Retrieval-Augmented Generation, RAG)입니다. RAG는 단순히 언어 모델의 자체 지식에만 의존하지 않고, 외부의 신뢰할 수 있는 데이터베이스에서 관련된 정보를 먼저 검색한 뒤 이를 바탕으로 답변을 생성하는 방식을 취합니다. 
RAG 시스템을 구축하기 위해서는 가장 먼저 보유한 방대한 문서를 적절한 크기의 텍스트 조각(Chunk)으로 나누는 작업이 필수적입니다. 이때 문맥이 끊기지 않도록 문단이나 문장 단위로 세밀하게 분할하고, 앞뒤 조각이 일정 부분 겹치게(Overlap) 설정하는 것이 검색 정확도를 높이는 핵심 노하우입니다. 이렇게 분할된 텍스트들은 임베딩 과정을 거쳐 벡터 데이터베이스(Vector DB)에 저장됩니다. 
사용자가 질문을 입력하면, 시스템은 동일한 방식으로 질문을 벡터로 변환한 후 데이터베이스에서 가장 거리가 가까운, 즉 의미적으로 가장 유사한 텍스트 조각들을 찾아냅니다. 마지막으로 이렇게 찾아낸 참고 문서들과 사용자의 원래 질문을 잘 조합하여 언어 모델에게 전달하면, 모델은 주어진 참고 문서의 내용만을 바탕으로 정확하고 출처가 명확한 답변을 작성하게 됩니다.
"""

'''
def split_by_sentence(long_text):
    sentences = kss.split_sentences(long_text)
    joined_sentences = '\n'.join(sentences)
    return joined_sentences


def documents_embedding(documents, model):
    return model.embed_documents(documents)

sentences = split_by_sentence(long_text)

chunks = text_splitter.split_text(sentences)

documents = [Document(page_content=chunk) for chunk in chunks]

vector_db.add_documents(documents)

query = "RAG는 어떻게 동작하나요?"

results = vector_db.similarity_search(
    query,
    k=2,
)

context = '\n\n'.join(
    doc.page_content for doc in results
)

messages = [
    {
        "role": "system",
        "content": (
            "너는 문서 기반 질의응답 AI다. "
            "주어진 참고 문서의 정보를 종합해서 질문에 직접 답한다. "
            "문장을 그대로 반복하지 말고 내용을 이해하기 쉽게 정리한다. "
            "문서에 정보가 없다면 모른다고 답한다."
        )
    },
    {
        "role": "user",
        "content": f"""
[참고 문서]
{context}

[질문]
{query}

답변:
"""
    }
]

response = generator(
    messages,
    max_new_tokens = 200,
    do_sample = False
)


answer = response[0]["generated_text"][-1]["content"]

print("===== 검색된 문서 =====")
print(context)

print("\n===== Qwen 답변 =====")
print(answer)
'''

def generate_db(doc: json):
    splitted_sentences = kss.split_sentences(text_documents)
    joined_sentences = '\n'.join(splitted_sentences)
    
    model_name = 'BAAI/bge-m3'

    model_kwargs = {'device':'cuda'}
    encode_kwargs = {'normalize_embeddings':True}

    embeddings = HuggingFaceEmbeddings(
        model_name = model_name,
        model_kwargs = model_kwargs,
        encode_kwargs = encode_kwargs
    )
    
    text_splitter = RecursiveCharacterTextSplitter(
    separators=["\n"],
    chunk_size=400,    
    chunk_overlap=20,    
    length_function=len
    )
    
    chunks = text_splitter.split_text(joined_sentences)
    
    documents = [
        Document(
            page_content = chunk,
            metadata={
                'id':i
            }
        ) for i, chunk in enumerate(chunks)
    ]
    
    vector_db = Chroma(
    collection_name = 'my_documents',
    embedding_function = embeddings,
    persist_directory = './chroma_db'
    )
    
    vector_db.add_documents(documents)
    
    return vector_db
    
    


def generate_answer(query, vector_db: Chroma):
    context = vector_db.similarity_search(
        query,
        k=3
    )
    
    for doc in context:
        print('내용: ',doc.page_content)
        print('metadata:',doc.metadata)
    
    model_id = 'Qwen/Qwen2.5-3B-Instruct'

    generator = pipeline(
    'text-generation',
    model=model_id,
    device_map = 'auto',
    dtype = 'auto')
    
    prompt = [
        {
            "role": "system",
            "content": (
                "너는 문서 기반 질의응답 AI다. "
                "주어진 참고 문서의 정보를 종합해서 질문에 직접 답한다. "
                "문장을 그대로 반복하지 말고 내용을 이해하기 쉽게 정리한다. "
                "문서에 정보가 없다면 모른다고 답한다."
            )
        },
        {
            "role": "user",
            "content": f"""
        [참고 문서]
        {context}

        [질문]
        {query}

        답변:
        """
        }
    ]
    
    response = generator(
        prompt,
        max_new_tokens= 256,
        do_sample = False,
        temperature = 0.1
    )
    
    answer = response[0]["generated_text"][-1]["content"]

    return answer

def generate_answer_v2(query, vector_db: Chroma):
    docs = vector_db.similarity_search(
        query,
        k = 3
    )
    
    context = '\n'.join([doc.page_content for doc in docs])
    
    url = 'https://genai.postech.ac.kr/agent/api/a1/gpt'
    api_key = os.getenv("API_KEY",None)
    
    headers = {
        'X-Api-Key': api_key,
        'Content-Type': 'application/json'
    }
    
    payload = {
        'message': f'''
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
            RAG 동작 과정
            1.
            2.
            3.
            ###
        ''',
        'stream': False,
        'files':[],
        'temperature':0.1,
        'top_k': 3
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code == 200:
            return response.json()['message']

        else:
            print(f"실패(상태 코드: {response.status_code})")
            return
    except Exception as e:
        print(f"에러 발생: {e}")
        return

def generate_answer_v3(query, vector_db: Chroma):
    docs = vector_db.similarity_search(
            query,
            k = 3
            )    
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
            RAG 동작 과정
            1.
            2.
            3.
            ###
        """,
        config = types.GenerateContentConfig(
            temperature = 0.2,
            top_k = 2,
            max_output_tokens = 2048,
            response_mime_type = 'application/json'
        )
    )
    return response.candidates[0].content.parts[0].text
    
    

if __name__ == '__main__':
   
    load_dotenv()
    
    long_text = """
인공지능 기술이 발전하면서 대규모 언어 모델(LLM)은 놀라운 문장 생성 능력을 보여주고 있습니다. 하지만 이러한 모델들은 학습된 시점 이후의 최신 정보를 알지 못하거나, 특정 기업의 내부 데이터와 같은 비공개 정보에는 접근할 수 없다는 치명적인 한계를 가지고 있습니다. 또한, 모델이 잘 모르는 내용을 그럴듯하게 지어내는 환각 현상(Hallucination)도 실무 도입을 가로막는 주요 원인 중 하나입니다.
이러한 문제를 해결하기 위해 등장한 기술이 바로 검색 증강 생성(Retrieval-Augmented Generation, RAG)입니다. RAG는 단순히 언어 모델의 자체 지식에만 의존하지 않고, 외부의 신뢰할 수 있는 데이터베이스에서 관련된 정보를 먼저 검색한 뒤 이를 바탕으로 답변을 생성하는 방식을 취합니다. 
RAG 시스템을 구축하기 위해서는 가장 먼저 보유한 방대한 문서를 적절한 크기의 텍스트 조각(Chunk)으로 나누는 작업이 필수적입니다. 이때 문맥이 끊기지 않도록 문단이나 문장 단위로 세밀하게 분할하고, 앞뒤 조각이 일정 부분 겹치게(Overlap) 설정하는 것이 검색 정확도를 높이는 핵심 노하우입니다. 이렇게 분할된 텍스트들은 임베딩 과정을 거쳐 벡터 데이터베이스(Vector DB)에 저장됩니다. 
사용자가 질문을 입력하면, 시스템은 동일한 방식으로 질문을 벡터로 변환한 후 데이터베이스에서 가장 거리가 가까운, 즉 의미적으로 가장 유사한 텍스트 조각들을 찾아냅니다. 마지막으로 이렇게 찾아낸 참고 문서들과 사용자의 원래 질문을 잘 조합하여 언어 모델에게 전달하면, 모델은 주어진 참고 문서의 내용만을 바탕으로 정확하고 출처가 명확한 답변을 작성하게 됩니다.
"""

    chr_db = generate_db(long_text)
    
    query = "RAG는 어떻게 동작하나요?" 
    
    answer = generate_answer_v2(query, chr_db)
    
    if answer:
        print(answer)

 
       
    







