from flask import *
import os
import base64
from PIL import Image, ExifTags
from PIL.ExifTags import TAGS
from io import BytesIO
import glob
from google.cloud import storage
from google.cloud import datastore
from google.cloud import secretmanager
import json


app= Flask(__name__)
app.config['SECRET_KEY'] = "secret key"
#os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = "projects/213668284036/secrets/credentials"
#os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = "AuthenticationCredentials.json"

@app.route("/", methods=['GET','POST'])
def home():
    fileslist=list_files()
    '''fileslist=""
    for file in fileslist1:
        fileslist += "<li><a href=\"/files1/" + file + "\">" + file + "</a></li>"'''
    return render_template("home.html",fileslist=fileslist)
	
def access_secret_version(project_id, secret_id, version_id="latest"):
    """
    Access the payload of the specified secret version.
    """
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    response = client.access_secret_version(request={"name": name})
    payload = response.payload.data.decode("UTF-8")
    return payload

project_id = "group10-project1"
secret_id = "authentication-credentials"
credentials_json = access_secret_version(project_id, secret_id)
credentials = json.loads(credentials_json)

@app.route("/uploads", methods=['POST'])
def uploads():
    if request.method=='POST':
        imagefile = request.files['form_file']
        fname = imagefile.filename
        kinds = "ImageMetadata"
        client = storage.Client(credentials=credentials)        
        client1 = datastore.Client(credentials=credentials)
        #print("filename: ",imagefile.filename)
        if len(fname)>0:
            imageuploadstatus = put_image_into_bucket(fname,imagefile,client)
            if imageuploadstatus:
                print("Image is pushed successfully into the bucket")
            else:
                print("Unable to store the image into the bucket.")
            
            #Code to put the metadata fetched into the datastore database.
            status = put_metadata_into_datastore(imagefile,kinds,client1,fname)
            if status:
                print("Data is pushed into the datastore database successfully")
            else:
                print("Unable to store the data in the datastore. Kindly contact system administrator to further verify the issue.")
                
            flash("Image and metadata saved successfully",'error')
            return redirect(url_for("home"))
        else:
            flash("Image was not choosen. Please select the image and then click submit",'error')
            return redirect(url_for("home"))
    else:
        flash("Unable to save the file. kindly contact system administrator ",'error')
        return redirect(url_for("home"))
		
@app.route("/files/<fname>")
def getfiles(fname):
    kinds = "ImageMetadata"
    client = storage.Client(credentials=credentials)        
    client1 = datastore.Client(credentials=credentials)
    image_data , mimetype = get_image_from_bucket(fname,client)
    image_bytes = image_data.read()
    # Encode the image data as base64
    image_base64 = base64.b64encode(image_bytes).decode('utf-8')
    try:
        feteched_data  = get_metadata_from_datastore(kinds,fname,client1)
        return render_template("output.html", image_base64 = image_base64, metadata = feteched_data,fname=fname)
    except:
        flash("Unable to fetch the file. Kindly try again later",'error')
        return redirect(url_for("home"))


def list_files():
    jpegfiles=[]
    client = storage.Client(credentials=credentials)        
    bucket = client.get_bucket("group10project2")
    blobs = list(bucket.list_blobs())
    for blob in blobs:
        if blob.name.lower().endswith(('.jpg', '.jpeg', '.png')):
            jpegfiles.append(blob.name.split("/")[1])
    return jpegfiles

def extract_metadata(image,fname):
    filename = fname
    image = Image.open(image)
    exif_data = image.getexif()
    metadata={}
    metadata['filename'] = filename
    if exif_data:
        for tag_id in exif_data:
                tag = TAGS.get(tag_id, tag_id)
                value = exif_data.get(tag_id)
                if isinstance(value, int) or isinstance(value,str) or isinstance(value, bool) or isinstance(value,float) or isinstance(value,bytes):
                    metadata[tag]=value
                else:
                    pass
    return metadata

def get_metadata_from_datastore(kinds,fname,client1):
    query = client1.query(kind=kinds)
    query.add_filter('filename', '=', fname)
    results = list(query.fetch())  # Execute the query and retrieve the results
    metadata1={}
    if results:
        # Convert the results to a dictionary for JSON response
        metadata1 = {key: value for key, value in results[0].items()}
    else:
        print("No results fetched.")
    return metadata1

def put_metadata_into_datastore(imagefile, kinds, client1, fname):
    data = extract_metadata(imagefile,fname)
    new_entity = datastore.Entity(client1.key(kinds))
    for key1,value1 in data.items():
        new_entity[key1]=value1
    try:
        client1.put(new_entity)
        return True
    except:
        return False

def put_image_into_bucket(fname,imagefile,client):
    
    bucket = client.get_bucket("group10project2")
    #setting the path for storing the image name. we have images folder created in the bucket.
    image_object_name = f'images/{fname}'
    #creating a blob variable with the image
    blob = bucket.blob(image_object_name)
    #uploading the file into the bucket.
    try:
        blob.upload_from_file(imagefile)
        return True
    except:
        return False
    
def get_image_from_bucket(fname,client):
    bucket = client.get_bucket("group10project2")
    #setting the path for storing the image name. we have images folder created in the bucket.
    image_object_name = f'images/{fname}'
    #creating a blob variable with the image
    blob = bucket.blob(image_object_name)
    if not blob.exists():
        print("Unable to find the image with the given filename")
    '''image_data = blob.download_as_string()
    images = io.BytesIO(image_data)
    mimetype="image/jpeg"'''
    image_bytes = BytesIO()
    blob.download_to_file(image_bytes)
    image_bytes.seek(0)
    mimetype="image/jpeg"
    return (image_bytes,mimetype)

app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))