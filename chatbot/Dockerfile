FROM public.ecr.aws/docker/library/python:3.12.2-slim-bullseye
RUN apt-get update && apt-get install --no-install-recommends -y vim gcc graphviz && apt-get clean && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY ./ /app/
RUN pip3 install -r requirements.txt --no-cache-dir
EXPOSE 8501
HEALTHCHECK --interval=600s --timeout=2s --retries=12 \
    CMD ["curl", "-f", "http://localhost:8501/"]
ENTRYPOINT ["streamlit", "run", "agent.py", "--server.headless", "true", "--browser.serverAddress='0.0.0.0'", "--browser.gatherUsageStats", "false"]
USER 1001