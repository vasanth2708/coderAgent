import json
from cognitoService import verify_cognito_token_bool
from fastapi import Request,FastAPI, Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import asyncio
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import http.client
from typing import Optional
from app.agents.multi_response import instructor_llm
from app.agents.rag_code import instructor_llm_github_new
from app.agents.rag_db import instructor_llm_rag
from app.agents.rag_document import create_rag_model, model_call
from app.agents.rules import desc_modifier
from app.agents.rag_analyser import check_gamp_data
import time
from sfAuthService import sf_auth
import boto3
from botocore.exceptions import ClientError

SECRET_KEY = "qwerfdsa1234cs56klvw67"
ALGORITHM = "HS256"

app = FastAPI()

API_KEY = "pGaVPcPohYCvq3AoUML6OfSImNyjR8IPHREJ7RKr88aoovn6SnJSKpKFFSakHs"

class SecretM(BaseModel):
    GENIE_CLIENT_ID: str
    GENIE_CLIENT_SECRET: str
    GENIE_CLIENT_URL: str

class AllAuthenticated(BaseModel):
    user_name: str
    url: str
    is_sandbox: bool

class InstructionInput(BaseModel):
    prompt : Optional[str]
    query : str
    data : Optional[str]
    table : Optional[str]

class Instruction(BaseModel):
    input: InstructionInput
    user_name: str
    url: str
    is_sandbox: bool


class SecretManagerRetriever(BaseModel):
    secret_name : str

class Instruct(BaseModel):
    prompt : Optional[str]
    query : str
    table : Optional[str]
    user_name: str
    url: str
    is_sandbox: bool


class Desc(BaseModel):
    prompt : str
    query : str
    user_name: str
    url: str
    is_sandbox: bool


class Documents(BaseModel):
    doc_name : str
    prompt: str
    query: str
    user_name: str
    url: str
    is_sandbox: bool


class Documents_gamp(BaseModel):
    #doc_name : str
    user_data: str
    prompt: str
    query: str
    user_name: str
    url: str
    is_sandbox: bool



app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.options("/{full_path:path}")
async def preflight_handler():
    return {"message": "CORS preflight OK"}

security = HTTPBearer()

def verify_secret_key(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or auth_header != f"Bearer {SECRET_KEY}":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing secret key"
        )


async def verify_api_key(x_api_key: str = Header(..., alias="X-API-KEY")):
    """
    Verify X-API-KEY header for API authentication.
    """
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key"
        )
    return x_api_key

#@app.get("/")
@app.get("/")
async def hello(authorization: str = Header(..., alias="Authorization"),
    x_api_key: str = Header(..., alias="X-API-KEY")):
    if not verify_cognito_token_bool(authorization):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Cognito token"
        )
    
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key"
        )
    return "Hello World!!!"

def prompt_struct(query):
    return query+"""
            **Context:**  
            {context}

            **Report:**
        """


@app.post("/all/authenticated")
async def all_authenticated(
    request: AllAuthenticated,
    authorization: str = Header(..., alias="Authorization"),
    x_api_key: str = Header(..., alias="X-API-KEY")
):
    # Verify Cognito token
    if not verify_cognito_token_bool(authorization):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Cognito token"
        )
    
    # Verify API key
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key"
        )
    
    # Authenticate with Salesforce
    response = await sf_auth(request.user_name, request.url, request.is_sandbox)
    
    if response.get("status") == 200:
        return JSONResponse(
            content={"authenticated": True, "message": "Authentication successful"},
            status_code=response.get("status")
        )
    else:
        return JSONResponse(
            content={"authenticated": False, "message": response.get("error")},
            status_code=response.get("status")
        )




@app.post("/urs_report")
async def urs_reporter(request: Documents, authorization: str = Header(..., alias="Authorization"),
    x_api_key: str = Header(..., alias="X-API-KEY")):
    if not verify_cognito_token_bool(authorization):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Cognito token"
        )
    
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key"
        )
    urs_path = "reportsgxpgenie"
    urs_vectorstore = await create_rag_model(urs_path,f"reports/{request.doc_name}.pdf")
    urs_report = await model_call(urs_vectorstore, prompt_struct(request.prompt), request.query)
    response = {
        "urs" : urs_report
    }
    return response

@app.post("/description")
async def description(desc: Desc, authorization: str = Header(..., alias="Authorization"),
    x_api_key: str = Header(..., alias="X-API-KEY")):
    if not verify_cognito_token_bool(authorization):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Cognito token"
        )
    
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key"
        )
    response = await desc_modifier(desc.prompt,desc.query)
    res = {
        "output" : response
    }
    return res

@app.post("/report")
async def report(request: Documents_gamp, authorization: str = Header(..., alias="Authorization"),
    x_api_key: str = Header(..., alias="X-API-KEY")):
    if not verify_cognito_token_bool(authorization):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Cognito token"
        )
    
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key"
        )
    """Optimized report generation with faster processing"""
    start_time = time.time()
    
    gamp_path = "reportsgxpgenie"
    s3_file = "rules/gamp5.pdf"
    gamp_report = await check_gamp_data(gamp_path, s3_file, request.query, request.user_data)
    
    end_time = time.time()
    print(f"Report generation completed in {end_time - start_time:.2f} seconds")
    
    response = {
        "gamp": gamp_report,
        "processing_time": f"{end_time - start_time:.2f} seconds"
    }
    print(response["gamp"])
    return response

@app.post("/instruction")
async def instruction(request: Instruction, authorization: str = Header(..., alias="Authorization"),
    x_api_key: str = Header(..., alias="X-API-KEY")):
    if not verify_cognito_token_bool(authorization):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Cognito token"
        )
    
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key"
        )
    response = await instructor_llm(request.input.prompt,request.input.data,request.input.query)
    return response

@app.post("/github")
async def instructor(request: Instruct, authorization: str = Header(..., alias="Authorization"),
    x_api_key: str = Header(..., alias="X-API-KEY")):
    if not verify_cognito_token_bool(authorization):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Cognito token"
        )
    
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key"
        )
    task = await instructor_llm_github_new(request.prompt, request.query)
    return task



def get_secret(secretname):

    secret_name = secretname#"gxpgenie"
    region_name = "us-east-2"

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        raise e

    secret_string = get_secret_value_response['SecretString']
    secret_dict = json.loads(secret_string)
    if 'GENIE_COGNITO_URL' in secret_dict and 'GENIE_CLIENT_URL' not in secret_dict:
        secret_dict['GENIE_CLIENT_URL'] = secret_dict.pop('GENIE_COGNITO_URL')
    secret = SecretM(**secret_dict)

    return secret

@app.post("/secrets")
async def secret_manager(req: SecretManagerRetriever, authorization: str = Header(..., alias="Authorization"),
    x_api_key: str = Header(..., alias="X-API-KEY")):
    if not verify_cognito_token_bool(authorization):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Cognito token"
        )
    
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key"
        )
    try:
        return get_secret(req.secret_name)
    except ClientError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Cognito token"
        )



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, timeout_keep_alive=120)
                                                                                                                                                            