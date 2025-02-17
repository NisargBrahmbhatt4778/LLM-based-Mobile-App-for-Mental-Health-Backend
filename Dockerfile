# Use an official Python runtime as a parent image
FROM python:3.9

# Set the working directory
WORKDIR /app

# Set environment variables


# Copy project files into the container
COPY . .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port FastAPI runs on
EXPOSE 8000

# Start the FastAPI app
CMD ["uvicorn", "responseAPI:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]