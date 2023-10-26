#Use the official Python 3.10 image based on Alpine linux
FROM python:3.10-alpine

# Set the working directory which is specific to the cloudrun repository
WORKDIR /app

# copy the requirements file used for dependencies in the code.
COPY requirements.txt .

# Install the needed packages which are specified in requirements.txt
RUN pip install --trusted-host pypi.python.org -r requirements.txt

#copy the contents into our working directory /app now.
COPY Project.py .
COPY ./templates ./templates

#COPY AuthenticationCredentials.json .
ENV GOOGLE_APPLICATION_CREDENTIALS=projects/213668284036/secrets/credentials


#PORT EXPOSURE
EXPOSE 8080

#RUNNING the file
CMD ["python", "Project.py"]