from flask import Flask
from flask import request, url_for, render_template, flash, redirect
import glob, os, pickle, sys
from werkzeug.utils import secure_filename
import numpy as np
import torch
import torchvision.models as models
import torch.nn.functional as F
from glob import glob
import cv2
from src.utility import preprocess_im, convert_image_np, getImageNetDict, load_basis
from src.utility import extract_features, getContribution, predict
import torch.optim as optim
import torch.nn as nn
import copy
import base64
from torchvision import transforms, utils
import tqdm, json
from torch.utils.data import Dataset, DataLoader, TensorDataset
from torch.autograd import Variable
from src.parallel_run import ProcessManager
import multiprocessing as mp

# load model and annotations
alexnet = models.alexnet(pretrained=True).cuda()
model = copy.deepcopy(alexnet).cuda()
model.classifier = nn.Sequential(*list(alexnet.classifier.children())[:-1])
W = list(alexnet.classifier.children())[-1].weight.cpu().data.numpy()
net = alexnet
print('after loading the model')
imagenetdict = getImageNetDict()

# load basis:
basis = load_basis(filedir='static/images/tiny-imagenet-200/train/*',
                   n_per_class=21)
basis_history = [[b, b] for b in basis]
basis_index = dict([(b,i) for i, b in enumerate(basis)])

features = extract_features(model, basis)
A = features.transpose(0,1).data.cpu().numpy()

newW = W.dot(A) # the new data
upload_dir = "static/images/tests"

Ainv = None

def getAinv():
    return np.linalg.pinv(A)

def setAinv(newAinv):
    global Ainv
    print("calculating Ainv done")
    Ainv = newAinv

PM = ProcessManager()

def update_Ainv(): # to run in PM
    print('>> updating A inv')
    PM._terminateAll() # kill existing calculation and rerun
    PM.add(target=getAinv, args=())
    PM.run(callback=setAinv)

# update_Ainv()

############################### web app begins ######################
app = Flask(__name__)
app.secret_key = 'secret' # not secret :(

@app.route('/favicon.ico')
def favicon():
    return 'something'

@app.route('/update_Ainv', methods=['POST'])
def app_update_Ainv():
    update_Ainv()
    return "update Ainv"
    
@app.route('/', methods=['POST', 'GET'])
def index():
    cat_id = [107, 249, 940, 1, 2, 113]
    top = 12
    if request.method == 'POST':
        cat_id = request.form['cat_id'].split(',')
        cat_id = list(map(int, cat_id))
        top = int(request.form['top'])
    classes = list(map(lambda c: imagenetdict[c], cat_id)) # not safe, todo

    # get all images to display
    id2image = {}
    for predict_id in cat_id:
        theta, images, _, selection = getContribution(newW, predict_id, A, Ainv,
                                           imagenetdict, basis, net, model,
                                           top=4096)
        id2image[predict_id] = list(zip(theta, images, selection))

    return render_template('gallery/index.html',
                           placeholder=",".join(map(str,cat_id)),
                           idimage_json=json.dumps(id2image),
                           classes_json=json.dumps(imagenetdict),
                           top=top)

@app.route('/image', methods=['POST', 'GET'])
def image_view():
    # really need to calculate inverse, return to this later if needed
    filenames = ['static/images/tests/shark.jpg']
    fn2image = {}
    top = 12
    if request.method == 'POST':
        top = int(request.form['top'])
        if 'img'  not in request.files:
            flash('No file part')
            return redirect(request.url)

        files = request.files.getlist("img")
        filenames = []
        for im in files:
            filename = secure_filename(im.filename)
            filename = os.path.join(upload_dir, filename)
            im.save(filename)            
            filenames.append(filename)

    if Ainv is None:
        text = "Ainv not ready yet"
        flash(text)
        return redirect('/')
    elif not PM.ready():
        text = "new Ainv not ready yet, using old Ainv, should be ready in 1 min"
        flash(text)        
        
    for filename in filenames:
        theta, images, input_weights, selection = getContribution(newW, predict_id=None,
                                                       A=A, Ainv=Ainv,
                                                       imagenetdict=imagenetdict,
                                                       basis=basis,
                                                       net=net, model=model,
                                                       test_image_name=filename,
                                                       coordinate=False,
                                                                  top=4096)
            
        fn2image[filename] = list(zip(theta, images, input_weights, selection))

    return render_template('gallery/image.html',
                           fn2image=fn2image,
                           fn2image_json=json.dumps(fn2image),    
                           top=top)

@app.route('/concepts', methods=['GET'])
def concepts_view():
    return render_template('gallery/concepts.html', basis=basis)

@app.route('/basis/<name>', methods=['GET'])
def concept_show(name): # show particular basis
    image_path = "/".join(name.split('^'))
    index = basis_index.get(image_path, None)
    if index is None:
        name = os.path.basename(image_path)
        image_path = "/".join(name.split('@'))[:-4] # todo: come up with a better scheme
        index = basis_index.get(image_path, None)
    return render_template('gallery/concept_show.html',
                           basis_set=basis_history[index],
                           index=index) 

@app.route('/basis/', methods=['POST'])
def swap_basis():
    impath = request.values['impath']
    index = int(request.values['index'])
    
    b = extract_features(model, [impath])[0].data.cpu().numpy()
    A[:,index] = b
    # update basis history
    basis_history[index][-1] = impath
    # async update Ainv
    global newW

    # if calcAinv:            
    #     Ainv = np.linalg.pinv(A)
    # update_Ainv()
    
    newW = W.dot(A)
    basis[index] = impath
    return "swap basis done"
    
@app.route('/concepts/<name>', methods=['POST', 'GET'])
def concept_edit(name):
    image_path = "/".join(name.split('^'))
    if request.method == 'POST':
        data_url = request.values['imageBase64']
        content = data_url.split(';')[1]
        image_encoded = content.split(',')[1]
        body = base64.decodebytes(image_encoded.encode('utf-8'))
        
        # save new image
        new_im_path = "static/images/basis/%s.png" % "@".join(name.split('^'))
        with open(new_im_path, "wb") as fh:
            fh.write(body)

        index = basis_index.get(image_path, None)
        if index is not None: # now we know it is a basis
            # return extract one column of basis
            b = extract_features(model, [new_im_path])[0].data.cpu().numpy()
            A[:,index] = b
            # update basis history
            basis_history[index][-1] = new_im_path
            # async update Ainv
            global newW

            # if calcAinv:            
            #     Ainv = np.linalg.pinv(A)
            # update_Ainv()                
                
            newW = W.dot(A)
            basis[index] = new_im_path
    
    return render_template('gallery/concept_edit.html', name=image_path)

@app.route('/model', methods=['POST', 'GET'])
def model_view():
    return "edit your model here"

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False, port=5050)

    
