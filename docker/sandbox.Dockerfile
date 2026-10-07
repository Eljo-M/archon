FROM python:3.12-slim
# Development image: install project-specific dependencies here before evaluation.
RUN mkdir /workspace && chown 65534:65534 /workspace
USER 65534:65534
WORKDIR /workspace
ENV PYTHONDONTWRITEBYTECODE=1
CMD ["python", "-m", "unittest", "discover", "-s", "tests"]
