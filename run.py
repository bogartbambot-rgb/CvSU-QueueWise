"""Start the QueueWise PWA: python run.py"""
import os
import uvicorn

from app import create_app

app = create_app()

if __name__ == '__main__':
    uvicorn.run(app, host=os.getenv('HOST', '127.0.0.1'), port=int(os.getenv('PORT', '8000')))
