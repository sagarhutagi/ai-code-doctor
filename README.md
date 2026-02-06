# ai-code-doctor

How to use :
1. Downlaod the repo
2. download the libraries given in requirements.txt
    pip install -r requirements.txt
3. Load the front end
    uvicorn backend.main:app --reload --port 8000
4. Load the back end 
    cd frontend && python -m http.server 3000

IMP : Make sure that you have ollama installed and have some models that you want to use in it