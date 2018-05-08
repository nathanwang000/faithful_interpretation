import os
import copy
import cv2
import numpy as np
from glob import glob
import tqdm

import torch
from torch.autograd import Variable
from torchvision import models

def preprocess_image(cv2im, resize_im=True):
    """
        Processes image for CNNs

    Args:
        PIL_img (PIL_img): Image to process
        resize_im (bool): Resize to 224 or not
    returns:
        im_as_var (Pytorch variable): Variable that contains processed float tensor
    """
    # mean and std list for channels (Imagenet)
    mean = [0.485, 0.456, 0.406]
    std = [0.229, 0.224, 0.225]
    # Resize image
    if resize_im:
        cv2im = cv2.resize(cv2im, (224, 224))
    im_as_arr = np.float32(cv2im)
    im_as_arr = np.ascontiguousarray(im_as_arr[..., ::-1])
    im_as_arr = im_as_arr.transpose(2, 0, 1)  # Convert array to D,W,H
    # Normalize the channels
    for channel, _ in enumerate(im_as_arr):
        im_as_arr[channel] /= 255
        im_as_arr[channel] -= mean[channel]
        im_as_arr[channel] /= std[channel]
    # Convert to float tensor
    im_as_ten = torch.from_numpy(im_as_arr).float()
    # Add one more channel to the beginning. Tensor shape = 1,3,224,224
    im_as_ten.unsqueeze_(0)
    # Convert to Pytorch variable
    im_as_var = Variable(im_as_ten, requires_grad=True)
    return im_as_var

def getImageNetDict():
    return eval(open('src/imagenet1000_clsid_to_human.txt').read())

def convert_image_np(inp):
    """Convert a Tensor to numpy image."""
    inp = inp.cpu().numpy().transpose((1, 2, 0))
    mean = np.array([0.485, 0.456, 0.406])
    std = np.array([0.229, 0.224, 0.225])
    inp = std * inp + mean
    inp = np.clip(inp, 0, 1)
    return inp

def preprocess_im(im, volatile=False):
    original_image = cv2.imread(im)
    prep_img = preprocess_image(original_image)
    if volatile:
        prep_img.volatile = True
    return prep_img.cuda()

def predict(net, im, imagenetdict):
    net.eval()
    prep_img = preprocess_im(im)
    prediction = net(prep_img).data.cpu().numpy().argmax()
    return imagenetdict[prediction], prediction
                
def extract_features(net, images):
    # output nxd features
    net.eval()
    seq = []
    for im in tqdm.tqdm(images):
        prep_img = preprocess_im(im, volatile=True)
        seq.append(prep_img)

    features = []
    for i in tqdm.tqdm(range(0, len(seq), 100)):
        images_batch = torch.cat(seq[i:i+100], dim=0)
        features.append(net(images_batch))
    return torch.cat(features, dim=0)

def load_imagenet_basis(filedir='static/images/tiny-imagenet-200/train/*',
               n_per_class=10):
    # visualize random images in each class of input
    types = glob(filedir)
    res = []
    for t in types:
        all_pics = glob(t + '/images/*')
        # for each 200 category, choose n_per_class
        rs = np.random.choice(range(len(all_pics)), n_per_class, replace=False)
        res.extend([all_pics[r] for r in rs])
    res = np.random.permutation(res)[:4096]
    print('done loading_basis')
    return list(res)

def load_basis(filedir='static/images/color_shape_combined/*'):
    images = np.random.permutation(glob(filedir))[:4096]
    print('done loading_basis')
    return list(images)

def lst_sq_solve(A, Ainv, b):
    # least square solve
    x = Ainv.dot(b)
    SST = ((b-b.mean())**2).sum()
    SSRes = ((b-A.dot(x))**2).sum()
    r_sq = 1 - SSRes / SST
    return x, r_sq
                        
def getContribution(newW, predict_id, 
                    A, Ainv, imagenetdict,
                    basis, net, model,
                    top=10, test_image_name=None, coordinate=True):
    
    if test_image_name is not None:
        word, predict_id = predict(net, test_image_name, imagenetdict)
        print(word, predict_id)
    else:
        word = imagenetdict[predict_id]
        
    # an example explaination: newW 1000 x num_basis
    weights = newW[predict_id]

    x, input_weights = None, None
    if test_image_name is not None:
        b = extract_features(model, [test_image_name])[0].data.cpu().numpy()
        x, r_sq = lst_sq_solve(A, Ainv, b)
        if coordinate:
            criteria = np.abs(x)
        else:
            criteria = np.abs(weights * x)
        args = np.argsort(criteria)[::-1]
    else:
        args = np.argsort(np.abs(weights))[::-1]


    selection = args[:top]
    print('%s =' % word)
    
    theta = weights[selection]
    theta = list(map(float, theta))
    images = np.array(basis)[selection]
    if x is not None:
        input_weights = x[selection]
        input_weights = list(map(float, input_weights))

    return theta, images, input_weights, list(map(int, selection))

