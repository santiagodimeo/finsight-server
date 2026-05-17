FROM public.ecr.aws/lambda/python:3.11
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY pipeline/ pipeline/
COPY api/ api/
CMD ["api.main.handler"]
