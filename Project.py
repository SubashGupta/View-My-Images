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
from google.oauth2 import service_account
import firebase_admin
from firebase_admin import credentials, auth
import json
from datetime import datetime


app= Flask(__name__)
app.config['SECRET_KEY'] = "secret key"

#The below code will help us to access the credentials.json file secretly and dynamically.	
def access_secret_version(project_id, secret_id, version_id="latest"):
    """
    Access the payload of the specified secret version.
    """
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    response = client.access_secret_version(request={"name": name})
    payload = response.payload.data.decode("UTF-8")
    return payload

#For stroage and datastore initialization fetching the credentials from secret manager
project_id = "group10-project1"
secret_id = "authentication-credentials"
credentials_json = access_secret_version(project_id, secret_id)
credentials_info = json.loads(credentials_json)
credentials1 = service_account.Credentials.from_service_account_info(credentials_info)

#For firebase initialization fetching the credentials from secret manager
project_id2 = "group10-project1"
secret_id2 = "firebase-config"
firebaseconfig_json = access_secret_version(project_id2, secret_id2)
firebase_config = json.loads(firebaseconfig_json)
cred = credentials.Certificate(firebase_config)
firebase_admin.initialize_app(cred)


@app.route('/', methods=['GET', 'POST'])
def initial():
    session.pop('user', None)
    session.pop('uid', None)
    return render_template("initial.html")
    
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    session.pop('user', None)
    session.pop('uid', None)
    if request.method == "POST":
        return jsonify({'status': 'success', 'message': 'Signup successful'})
    else:
        return render_template("signup1.html")

@app.route('/login', methods=['GET','POST'])
def login():
    session.pop('user', None)
    session.pop('uid', None)
    if request.method == "POST":
        try:
            authorization_header = request.headers.get('Authorization', '')
            if 'Bearer ' in authorization_header:
                id_token = authorization_header.split('Bearer ')[1]
                verified_token = auth.verify_id_token(id_token)
                session['user'] = verified_token['email']
                session['uid'] = verified_token['uid']
                return redirect(url_for('home'))
            else:
                raise ValueError('Bearer token not found in Authorization header')
                flash("Issue in login. Login failed. Please try again. ",'error')
                return redirect(url_for("login"))

        except auth.ExpiredIdTokenError as e:
            print(f"Token expired: {e}")
            flash(f"Token expired: {e} Please try again. ",'error')
            return redirect(url_for("login"))
        except auth.InvalidIdTokenError as e:
            print(f"Invalid token: {e}")
            flash(f"Invalid token: {e} Please try again. ",'error')
            return redirect(url_for("login"))
        except Exception as e:
            print(f"Unexpected error: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500
    else:
        return render_template("login1.html")

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    session.pop('user', None)
    session.pop('uid', None)
    flash("Successfully logged out the user. ",'error')
    return redirect(url_for('login'))

@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    if 'user' in session:
        if request.method == 'POST':
            email = session['user']
            uid = session['uid']
            #old_password = request.form.get('old_password')
            new_password = request.form.get('new_password')
            confirm_new_password = request.form.get('confirm_new_password')
            if new_password == confirm_new_password:
                try: 
                    auth.update_user(uid, password=new_password)
                    flash('Password changed successfully!', 'success')
                    return redirect(url_for('login'))

                except ValueError as e:
                    flash(f'Error changing password: {e}', 'error')
            else:
                flash('New and Confirm Password Mismatch. Try again!', 'error')
                return redirect(url_for('change_password'))
        else:# Handle other HTTP methods or invalid requests
            return render_template('change_password.html')
    else:
        flash('Please login before you proceed further. ', 'error')
        return redirect(url_for('login'))
        

@app.route("/home", methods=['GET','POST'])
def home():
    if 'user' in session:
        usernames = session['user']
        fileslist=list_files(usernames)
        return render_template("home.html",fileslist=fileslist)    
    else:
        flash('Please login before you proceed further. ', 'error')
        return redirect(url_for('login'))

@app.route("/uploads", methods=['POST'])
def uploads():
    if 'user' in session:
        if request.method=='POST':
            imagefile = request.files['form_file']
            fname = imagefile.filename
            kinds = "ImageMetadata"
            client = storage.Client(credentials=credentials1)        
            client1 = datastore.Client(credentials=credentials1)
            foldername = session['user']
            #print("filename: ",imagefile.filename)
            if len(fname)>0:
                fileslist=list_files(foldername)
                if fname in fileslist:
                    flash(f'An Image with the same name {fname} already uploaded by the current user. Please rename the file ad try again.','error')
                    return redirect(url_for("home"))
                else:
                    imageuploadstatus = put_image_into_bucket(fname,imagefile,client,foldername)
                    if imageuploadstatus:
                        print("Image is pushed successfully into the bucket")
                    else:
                        print("Unable to store the image into the bucket.")
                    
                    #Code to put the metadata fetched into the datastore database.
                    status = put_metadata_into_datastore(imagefile,kinds,client1,fname,foldername)
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
    else:
        flash('Please login before you proceed further. ', 'error')
        return redirect(url_for('login'))
		
@app.route("/files/<fname>")
def getfiles(fname):
    if 'user' in session:
        foldername = session['user']
        kinds = "ImageMetadata"
        client = storage.Client(credentials=credentials1)        
        client1 = datastore.Client(credentials=credentials1)
        image_data , mimetype = get_image_from_bucket(fname,client,foldername)
        image_bytes = image_data.read()
        # Encode the image data as base64
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        try:
            feteched_data  = get_metadata_from_datastore(kinds,fname,client1,foldername)
            return render_template("output.html", image_base64 = image_base64, metadata = feteched_data,fname=fname)
        except:
            flash("Unable to fetch the file. Kindly try again later",'error')
            return redirect(url_for("home"))
    else:
        flash('Please login before you proceed further. ', 'error')
        return redirect(url_for('login'))

@app.route("/delete", methods=['GET','POST'])
def delete():
    if 'user' in session:
        foldername = session['user']
        fname = request.form['fname']
        client = storage.Client(credentials=credentials1)
        client1 = datastore.Client(credentials=credentials1)
        bucket = client.get_bucket("group10project2")
        image_object_name = f'{foldername}/{fname}'
        blob = bucket.blob(image_object_name)
        kinds = "ImageMetadata"
        query = client1.query(kind=kinds)
        query.add_filter('filename', '=', fname)
        query.add_filter('username', '=', foldername)
        
        try:
            blob.delete()
            entities = list(query.fetch())
            for entity in entities:
                client1.delete(entity.key)
            flash(f'Successfully deleted the image and the metadata of {fname}','error')
            return redirect(url_for("home"))
        except:
            flash(f'Unable to find the image or the metadata to delete. Please try again later.','error')
            return redirect(url_for("home"))
    else:
        flash('Please login before you proceed further. ', 'error')
        return redirect(url_for('login'))

def list_files(usernames):
    jpegfiles=[]
    '''client = storage.Client(credentials=credentials1)        
    bucket = client.get_bucket("group10project2")
    blobs = list(bucket.list_blobs())
    for blob in blobs:
        if blob.name.lower().endswith(('.jpg', '.jpeg', '.png')):
            jpegfiles.append(blob.name.split("/")[1])
    '''
    kinds = "ImageMetadata"      
    client1 = datastore.Client(credentials=credentials1)
    query = client1.query(kind=kinds)
    query.add_filter('username', '=', usernames)  #Queries all the file names which are stored by that user.
    results = list(query.fetch())
    #print(results)
    filenames = [entity['filename'] for entity in results if 'filename' in entity]
    #print(filenames)
    return filenames

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

def get_metadata_from_datastore(kinds,fname,client1,foldername):
    query = client1.query(kind=kinds)
    query.add_filter('filename', '=', fname)
    query.add_filter('username', '=', foldername)
    results = list(query.fetch())  # Execute the query and retrieve the results
    metadata1={}
    if results:
        # Convert the results to a dictionary for JSON response
        metadata1 = {key: value for key, value in results[0].items()}
    else:
        print("No results fetched.")
    return metadata1

def put_metadata_into_datastore(imagefile, kinds, client1, fname,foldername):
    data = extract_metadata(imagefile,fname)
    new_entity = datastore.Entity(client1.key(kinds))
    for key1,value1 in data.items():
        new_entity[key1]=value1
    new_entity['username']=foldername
    times=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    new_entity['uploaded_date']=times
    try:
        client1.put(new_entity)
        return True
    except:
        return False

def put_image_into_bucket(fname,imagefile,client,foldername):
    
    bucket = client.get_bucket("group10project2")
    #setting the path for storing the image name. we have images folder created in the bucket.
    image_object_name = f'{foldername}/{fname}'
    #creating a blob variable with the image
    blob = bucket.blob(image_object_name)
    #uploading the file into the bucket.
    try:
        blob.upload_from_file(imagefile)
        return True
    except:
        return False
    
def get_image_from_bucket(fname,client,foldername):
    bucket = client.get_bucket("group10project2")
    #setting the path for storing the image name. we have images folder created in the bucket.
    image_object_name = f'{foldername}/{fname}'
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