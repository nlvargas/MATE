from django.shortcuts import render

def index(request, param=None):
    return render(request, 'index.html')