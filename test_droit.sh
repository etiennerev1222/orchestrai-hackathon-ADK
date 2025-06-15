#!/bin/bash
# Create a Role with permissions for persistentvolumeclaims
kubectl create role pvc-access-role \
--namespace default \
--verb=get,list,watch,create,delete \
--resource=persistentvolumeclaims
# Bind the Role to the service account
kubectl create rolebinding pvc-access-binding \
--namespace=default \
--role=pvc-access-role \
--serviceaccount=434296769439-compute@developer.gserviceaccount.com

