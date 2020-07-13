import numpy as np
import scipy
import matplotlib.pyplot as plt
from mathFunc import getDetec,xcorrSimple,xcorrComplex,flat,validL,randomSource
from numba import jit,float32, int64
from scipy import fftpack,interpolate
from fk import FK,getSourceSacName,FKL
import os 
from scipy import io as sio
import obspy
from multiprocessing import Process, Manager
import random
import seism
from glob import glob
'''
the specific meaning of them you can find in Chen Xiaofei's paper
(A systematic and efficient method of computing normal modes for multilayered half-space)
'''
gpdcExe = '/home/jiangyr/program/geopsy/bin/gpdc'
class config:
    def __init__(self,originName='models/prem',srcSacDir='/home/jiangyr/home/Surface-Wave-Dispersion/',\
        distance=np.arange(400,1500,100),srcSacNum=100,delta=0.5,layerN=1000,\
        layerMode='prem',getMode = 'norm',surfaceMode='PSV',nperseg=200,noverlap=196,halfDt=150,\
        xcorrFuncL = [xcorrSimple,xcorrComplex],isFlat=False,R=6371,flatM=-2,pog='p',calMode='fast',\
        T=np.array([0.5,1,5,10,20,30,50,80,100,150,200,250,300]),threshold=0.1,expnt=10,dk=0.1,\
        fok='/k',gpdcExe=gpdcExe,order=0,minSNR=5,isCut=False,minDist=0,maxDist=1e8,\
        minDDist=0,maxDDist=1e8,para={},isFromO=False,removeP=False,doFlat=True,\
        QMul=1):
        para0= {\
            'delta0'    :0.02,\
            'freq'      :[-1, -1],\
            'filterName':'bandpass',\
            'corners'   :2,\
            'zerophase' :True,\
            'maxA'      :1e5,\
        }
        para0.update(para)
        self.originName = originName
        self.srcSacDir  = srcSacDir
        self.distance   = distance
        self.srcSacNum  = srcSacNum
        self.delta      = delta
        self.layerN     = layerN
        self.layerMode  = layerMode
        self.getMode    = getMode
        self.surfaceMode= surfaceMode
        self.nperseg    = nperseg
        self.noverlap   = noverlap
        self.halfDt     = halfDt
        self.xcorrFuncL = xcorrFuncL
        self.isFlat     = isFlat
        self.R          = R
        self.flatM      = flatM
        self.pog        = pog
        self.calMode    = calMode
        self.T          = T
        self.threshold  = threshold
        self.expnt      = expnt
        self.dk         = dk
        self.fok        = fok
        self.gpdcExe    = gpdcExe
        self.order      = order
        self.minSNR     = minSNR
        self.isCut      = isCut
        self.minDist    = minDist
        self.maxDist    = maxDist
        self.minDDist   = minDDist
        self.maxDDist   = maxDDist
        self.para0      = para0
        self.isFromO    = isFromO
        self.removeP    = removeP
        self.doFlat    = doFlat
        self.QMul      = QMul
    def getDispL(self):
        return [disp(nperseg=self.nperseg,noverlap=self.noverlap,fs=1/self.delta,\
            halfDt=self.halfDt,xcorrFunc = xcorrFunc) for xcorrFunc in self.xcorrFuncL]
    def getModel(self,modelFile=''):
        if len(modelFile)==0:
            modelFile = self.originName
        return model(modelFile, mode=self.surfaceMode,getMode = self.getMode,\
            layerMode =self.layerMode,layerN=self.layerN,isFlat=self.isFlat,R=self.R,flatM=self.flatM,\
            pog=self.pog,gpdcExe=self.gpdcExe,doFlat=self.doFlat,QMul=self.QMul)
    def genModel(self,modelFile='',N=100,perD= 0.10,depthMul=2):
        if len(modelFile)==0:
            modelFile = self.originName
        #800.0       11.0       6.13      4.46      740.0     312.0
        model0 = np.loadtxt(modelFile)
        for i in range(N):
            model = model0.copy()
            depthLast = 0
            for j in range(model.shape[0]):
                depth0     = model[j,0]
                depth      = max(depthLast,depthLast + (depth0-depthLast)*(1+perD*depthMul*(2*np.random.rand()-1)))
                if j ==0:
                    depth=0
                depthLast  = depth
                model[j,0] = depth
                for k in range(2,model.shape[1]):
                    if k<4:
                        if j ==0:
                            d = 1
                        else:
                            d = model0[j,k]- model0[j-1,k]
                        if j!=0:
                            model[j,k]=model[j-1,k]+(1+perD*(2*np.random.rand()-1))*d
                        else:
                            model[j,k]=model[j,k]+(0+perD*(2*np.random.rand()-1))*d
                    else:
                        model[j,k] = int(model[j,k]*(np.random.rand()+8)/8.5)
                model[j,1] = model[j,2]*(1.7+2*(np.random.rand()-0.5)*0.18)
            np.savetxt('%s%d'%(modelFile,i),model)
    def genFvFile(self,modelFile='',fvFile=''):
        if len(modelFile)==0:
            modelFile = self.originName
        if len(fvFile) ==0:
            if not self.isFlat:
                fvFile='%s_fv'%(modelFile)
            else:
                fvFile='%s_fv_flat'%(modelFile)
            fvFile+= '_'+self.getMode
            fvFile+= '_'+self.pog
            fvFile='%s_%d'%(fvFile,self.order)
        m = self.getModel(modelFile)
        print(m.modelFile)
        f,v=m.calDispersion(order=0,calMode=self.calMode,threshold=self.threshold,T=self.T,pog=self.pog)
        f = fv([f,v],'num')
        f.save(fvFile)
    def calFv(self,iL,pog=''):
        pog0 = self.pog
        if len(pog)==0:
            pog = pog0
        self.pog = pog
        for i in iL:
            modelFile = self.getModelFileByIndex(i)
            self.genFvFile(modelFile)
        self.pog=pog0
    def getModelFileByIndex(self,i):
        return '%s%d'%(self.originName,i)
    def plotModelL(self,modelL):
        plt.close()
        for model in modelL:
            z,vp,vs = model.outputZV()
            plt.plot(vp,z,'b',linewidth=0.3,alpha=0.3,label='rand_vp')
            plt.plot(vs,z,'r',linewidth=0.3,alpha=0.3,label='rand_vp')
        z,vp,vs = self.getModel().outputZV()
        #plt.plot(vp,z,'k',linewidth=2,label=self.originName+'_vp')
        #plt.plot(vs,z,'k',linewidth=2,label=self.originName+'_vs')
        #plt.legend()
        plt.title(self.originName)
        plt.gca().invert_yaxis() 
        plt.xlabel('v/(m/s)')
        plt.ylabel('depth')
        plt.savefig(self.originName+'.jpg',dpi=300)
    def plotFVL(self,fvD,pog=''):
        if len(pog)==0:
            pog=self.pog
        plt.close()
        for key in fvD:
            FV =fvD[key]
            f = FV.f
            v = FV.v
            plt.plot(v,f,'b',linewidth=0.3,alpha=0.3,label='rand')
        originFv = self.getFV(pog=pog)
        f = originFv.f
        v = originFv.v
        plt.plot(v,f,'r',linewidth=2,label=self.originName)
        #plt.legend()
        plt.xlabel('v/(m/s)')
        plt.ylabel('f/Hz')
        plt.gca().semilogy()
        plt.gca().invert_yaxis()
        plt.title(self.originName+pog)
        plt.savefig('%s_fv_%s.jpg'%(self.originName,pog),dpi=300)
    def getFV(self,index=-1,pog=''):
        if len(pog)==0:
            pog=self.pog
        if index == -1:
            tmpName = self.originName+'_fv'
        else:
            tmpName ='%s%d_fv'%(self.originName,index)
        if self.isFlat:
            tmpName+='_flat'
        tmpName+='_%s_%s_%d'%(self.getMode,pog,self.order)
        print(tmpName)
        return fv(tmpName,'file')
    def quakeCorr(self,quakes,stations,byRecord=True,remove_resp=False,para={},minSNR=-1,
        isLoadFv=False,fvD={},isByQuake=False,quakesRef=[]):
        corrL = []
        disp = self.getDispL()[0]
        if minSNR <0:
            minSNR = self.minSNR
        self.para0.update(para)
        for quake in quakes:
            if isByQuake:
                quakeName=quake.name('_')
            else:
                quakeName=''
            if len(quakesRef)>0:
                index = quakesRef.find(quake)
                if index>=0:
                    quake = quakesRef[index]
                else:
                    continue
            sacsL = quake.getSacFiles(stations,isRead = True,strL='ZNE',\
                byRecord=byRecord,minDist=self.minDist,maxDist=self.maxDist,\
                remove_resp=remove_resp,para=self.para0)
            #print('###',sacsL)
            sacNamesL = quake.getSacFiles(stations,isRead = False,strL='ZNE',\
                byRecord=byRecord,minDist=self.minDist,maxDist=self.maxDist,\
                remove_resp=remove_resp)
            if self.isFromO:
                for sacs in sacsL:
                    sacs[0] = seism.sacFromO(sacs[0])
            
            corrL += corrSacsL(disp,sacsL,sacNamesL,modelFile=self.originName,\
                minSNR=minSNR,minDist=self.minDist,maxDist=self.maxDist,\
                minDDist=self.minDDist,maxDDist=self.maxDDist,\
                srcSac=quake.name(s='_'),isCut=self.isCut,isFromO=self.isFromO,\
                removeP=self.removeP,fvD=fvD,isLoadFv=isLoadFv,quakeName=quakeName)
            print('###########',len(corrL))
        return corrL
    def modelCorr(self,count=1000,randDrop=0.3,noises=None,para={},minSNR=-1):
        corrL = []
        disp = self.getDispL()[0]
        if minSNR <0:
            minSNR = self.minSNR
        for i in range(count):
            modelFile = self.getModelFileByIndex(i)
            sacsLFile = modelFile+'sacFile'
            sacsL,sacNamesL,srcSac = self.getSacFile(sacsLFile,randDrop=randDrop,para=para)
            if self.isFromO:
                for sacs in sacsL:
                    sacs[0] = seism.sacFromO(sacs[0])
            if not isinstance(noises,type(None)):
                noises(sacsL,channelL=[0])
            corrL += corrSacsL(disp,sacsL,sacNamesL,modelFile=modelFile\
                ,srcSac=srcSac,minSNR=minSNR,isCut=self.isCut,\
                minDist=self.minDist,maxDist=self.maxDist,\
                minDDist=self.minDDist,maxDDist=self.maxDDist\
                ,isFromO=self.isFromO,removeP=self.removeP)
            print('###########',len(corrL))
        return corrL
    def getSacFile(self,sacFile,randDrop=0.3,para={}):
        sacsL = []
        sacNamesL = []
        self.para0.update(para)
        print(self.para0)
        with open(sacFile) as f:
            lines = f.readlines()
        srcData = ''
        if np.random.rand()<randDrop:
            duraCount = int(5+200*(np.random.rand()**2))
            srcData = np.zeros(duraCount)
            if np.random.rand()<randDrop:
                if np.random.rand()<randDrop:
                    randomSource(3,duraCount,srcData)
                else:
                    randomSource(2,duraCount,srcData)
            else:
                randomSource(4,duraCount,srcData)
            print('convolve data')
        for line in lines:
            if line[0]=='#':
                srcSac = line[1:]
                continue
            if np.random.rand()<randDrop:
                continue
            sacNames = line.split()
            sacNamesL.append(sacNames)
            sacsL.append( [obspy.read(sacName)[0] for sacName in sacNames])
            if self.para0['freq'][0] > 0:
                for sac in sacsL[-1]:
                    if len(srcData)>0:
                        sac.data=np.convolve(sac.data,srcData,'same')
                    sac.filter(self.para0['filterName'],\
                        freqmin=self.para0['freq'][0], freqmax=self.para0['freq'][1], \
                        corners=self.para0['corners'], zerophase=self.para0['zerophase'])
        return sacsL,sacNamesL,srcSac
    def getNoise(self,quakes,stations,mul=0.2,byRecord=False,remove_resp=False,para={}):
        self.para0.update(para)
        sacsL = quakes.getSacFiles(stations,isRead = True,strL='ZNE',\
                byRecord=byRecord,minDist=self.minDist,maxDist=self.maxDist,\
                remove_resp=remove_resp,para=self.para0)
        return seism.Noises(sacsL,mul=mul)
    def loadNEFV(self,stations):
        fvD = {}
        for i in range(len(stations)):
            for j in range(len(stations)):
                file = glob('models/NEFV/*%s*%s*'%(stations[i]['sta'],stations[j]['sta']))
                #print('models/NEFV/*%s_%s*'%(stations[i]['sta'],stations[j]['sta']))
                pairKey = '%s_%s'%(stations[i]['sta'],stations[j]['sta'])
                if len(file)>0:
                    fvD[pairKey] = fv(file[0],mode='NEFile')
                    if (i*j)%100==0:
                        print(pairKey)
        return fvD
    def loadQuakeNEFV(self,stations):
        fvD = {}
        quakeD={}
        for i in range(len(stations)):
            for j in range(len(stations)):
                #\YP.NE11\YP.NE11_YP.NE3A\Rayleigh
                #print('models/QuakeNEFV/???%s/*_*%s/Rayleigh/pvt_sel.dat'%(stations[i]['sta'],stations[j]['sta']))
                file = glob('models/QuakeNEFV/???%s/*_*%s/Rayleigh/pvt_sel.dat'%(stations[i]['sta'],stations[j]['sta']))
                #print('models/NEFV/*%s_%s*'%(stations[i]['sta'],stations[j]['sta']))
                if len(file)==1:
                    print(file[0])
                    getFVFromPairFile(file[0],fvD,quakeD)
        return fvD,seism.QuakeL([quakeD[key] for key in quakeD])


        

class layer:
    '''
    class for layered media;
    the p velocity(vp), s velocity(vs), density(rho), [top depth, bottom depth](z) is needed; 
    p and s 's Q(Qp, Qs) is optional(default is 1200,600)
    After specifying the above parameters, the lame parameter(lambda, miu), zeta and xi would
     be calculate as class's attributes. 
    '''
    def __init__(self,vp,vs,rho,z=[0,0],Qp=1200,Qs=600):
        self.z    = np.array(z)
        self.vp   = np.array(vp)
        self.vs   = np.array(vs)
        self.rho  = np.array(rho)
        self.Qp = Qp
        self.Qs = Qs
        self.lamb, self.miu = self.getLame()
        self.zeta = self.getZeta()
        self.xi   = self.getXi()
    @jit
    def getLame(self):
        miu  = self.vs**2*self.rho
        lamb = self.vp**2*self.rho-2*miu
        return lamb, miu
    @jit
    def getZeta(self):
        return 1/(self.lamb + 2*self.miu)
    @jit
    def getXi(self):
        zeta = self.getZeta()
        return 4*self.miu*(self.lamb + self.miu)*zeta
    @jit
    def getNu(self, k, omega):
        return (k**2-(omega/self.vs.astype(np.complex))**2)**0.5
    @jit
    def getGamma(self, k,omega):
        return (k**2-(omega/self.vp.astype(np.complex))**2)**0.5
    @jit
    def getChi(self, k,omega):
        ### is it right
        nu = self.getNu(k, omega)
        return k**2 + nu**2
        #return k**2 + np.abs(nu)**2
    @jit
    def getEA(self, k,omega, z,mode = 'PSV'):
        nu    = self.getNu(k, omega)
        gamma = self.getGamma(k, omega)
        chi   = self.getChi(k,omega)
        alpha = self.vp
        beta  = self.vs
        miu   = self.miu
        if mode == 'PSV':
            E = 1/omega*np.array(\
                  [[ alpha*k,              beta*nu,          alpha*k,             beta*nu],\
                  [  alpha*gamma,          beta*k,           -alpha*gamma,        -beta*k],  \
                  [  -2*alpha*miu*k*gamma, -beta*miu*chi,    2*alpha*miu*k*gamma, beta*miu*chi],
                  [  -alpha*miu*chi,       -2*beta*miu*k*nu, -alpha*miu*chi,      -2*beta*miu*k*nu]])
            A = np.array(\
                [[np.exp(-gamma*(z-self.z[0])), 0,                         0,                           0],\
                 [0,                            np.exp(-nu*(z-self.z[0])), 0,                           0],\
                 [0,                            0,                         np.exp(gamma*(z-self.z[1])), 0],\
                 [0,                            0,                         0,                           np.exp(nu*(z-self.z[1]))]\
                ])
        elif mode == 'SH':
            E = np.array(\
                [[1,       1],\
                [ -miu*nu, miu*nu]])
            A = np.array(\
                [[np.exp(-nu*(z-self.z[0])), 0],\
                [ 0,                         np.exp(nu*(z-self.z[1]))]])
        return E, A

class surface:
    '''
    class for surface of layer
    the layers above and beneath(layer0, layer1) is needed
    Specify the bool parameters isTop and isBottom, if the surface is the first or last one； the default is false
    the default waveform mode(mode) is 'PSV', you can set it to 'SH'
    '''
    def __init__(self, layer0, layer1,mode='PSV',isTop = False, isBottom = False):
        self.layer0 = layer0
        self.layer1 = layer1
        #if not isTop:
        self.z      = layer0.z[-1]
        self.Td       = 0
        self.Tu       = 0
        self.Rud      = 0
        self.Rdu      = 0
        self.TTd      = 0
        self.TTu      = 0
        self.RRud     = 0
        self.RRdu     = 0
        self.mode     = mode
        self.isTop    = isTop
        self.isBottom = isBottom
        self.E = [None,None]
        self.A = [None,None]
    @jit
    def submat(self,M):
        shape = M.shape
        lenth = int(shape[0]/2)
        newM  = M.reshape([2, lenth, 2, lenth])
        newM  = newM.transpose([0,2,1,3])
        return newM
    @jit
    def setTR(self, k, omega):
        E0, A0 = self.layer0.getEA(k, omega, self.z, self.mode)
        E1, A1 = self.layer1.getEA(k, omega, self.z,self.mode)
        E0     = self.submat(E0)
        #print(E0[0][0].shape)
        E1     = self.submat(E1)
        A0     = self.submat(A0)
        A1     = self.submat(A1)
        self.E = [E0, E1]
        self.A = [A0, A1]
        EE0    = self.toMat([[E1[0][0],   -E0[0][1]],\
            [                 E1[1][0],   -E0[1][1]]])
        EE1    = self.toMat([[E0[0][0],   -E1[0][1]],\
            [                 E0[1][0],   -E1[1][1]]])
        AA     = self.toMat([[A0[0][0],   A0[0][0]*0],\
            [                 A1[0][0]*0, A1[1][1]]])
        #print(AA)
        TR     = EE0**(-1)*EE1*AA
        TR     = self.submat(np.array(TR))
        self.Td  = TR[0][0]
        self.Rdu = TR[1][0]
        self.Rud = TR[0][1]
        self.Tu  = TR[1][1]
        if self.isTop:
            self.Rud = -E1[1][0]**(-1)*E1[1][1]*(A1[1][1])
            self.Td = self.Rud*0
            self.Tu = self.Rud*0
    @jit
    def toMat(self,l):
        shape0 = len(l)
        shape1 = len(l[0])
        shape = np.zeros(2).astype(np.int64)
        #print(l[0][0].shape)
        shape[0]  = l[0][0].shape[0]
        shape[1]  = l[0][0].shape[1]
        SHAPE  = shape+0
        SHAPE[0] *=shape0
        SHAPE[1] *=shape1
        M = np.zeros(SHAPE,np.complex)
        for i in range(shape0):
            for j in range(shape1):
                i0 = i*shape[0]
                i1 = (i+1)*shape[0]
                j0 = j*shape[1]
                j1 = (j+1)*shape[1]
                #print(i0,i1,j0,j1)
                M[i0:i1,j0:j1] = l[i][j]
        return np.mat(M)
    @jit
    def setTTRRD(self, surface1 = 0):
        if self.isBottom :
            RRdu1 = np.mat(self.Rdu*0)
            #return 0
        else:
            RRdu1 =  surface1.RRdu
        self.TTd  = (np.mat(np.eye(self.Rud.shape[0])) - np.mat(self.Rud)*np.mat(RRdu1))**(-1)*np.mat(self.Td)
        self.RRdu = np.mat(self.Rdu) + np.mat(self.Tu)*np.mat(RRdu1)*self.TTd
    @jit
    def setTTRRU(self, surface0 = 0):
        if self.isTop :
            self.RRud = self.Rud
            return 0
        self.TTu  = (np.mat(np.eye(self.Rud.shape[0])) - np.mat(self.Rdu)*np.mat(surface0.RRud))**(-1)*np.mat(self.Tu)
        self.RRud = np.mat(self.Rud) + np.mat(self.Td)*np.mat(surface0.RRud)*self.TTu

class model:
    '''
    class for layered media model
    modeFile is the media parameter model File, there are tow mods
    if layerMode == 'norm':
       '0    18  2.80  6.0 3.5'
       layer's top depth, layer's bottom depth, density, p velocity, svelocity
    if layerMode =='prem':
        '0.00       5.800     3.350       2.800    1400.0     600.0'
        depth,  p velocity, s velocity, density,    Qp,        Qs
    mode is for PSV and SH
    getMode is the way to get phase velocity:
        norm is enough to get phase velocity
        new is to get fundamental phase velocity for PSV
    '''
    def __init__(self,modelFile, mode='PSV',getMode = 'norm',layerMode ='prem',layerN=10000,isFlat=False,R=6371,flatM=-2,\
        pog='p',gpdcExe=gpdcExe,doFlat=True,QMul=1):
        #z0 z1 rho vp vs Qkappa Qmu
        #0  1  2   3  4  5      6
        self.modelFile = modelFile
        self.getMode = getMode
        self.isFlat =isFlat
        self.gpdcExe = gpdcExe
        self.mode= mode
        data = np.loadtxt(modelFile)
        layerN=min(data.shape[0]+1,layerN+1)
        layerL=[None for i in range(layerN)]
        if layerMode == 'old':
            layerL[0] = layer(1.7, 1, 0.0001,[-100,0])
            for i in range(1,layerN):
                layerL[i] = layer(data[i-1,3], data[i-1,4], data[i-1,2], data[i-1,:2])
        elif layerMode == 'prem' or layerMode == 'norm':
            layerL[0] = layer(1.7, 1, 0.0001,[-100,0])
            zlast = 0
            for i in range(1,layerN):
                #100.0        7.95      4.45      3.38      200.0      80.0
                #0            1         2         3         4          5
                #vp,vs,rho,z=[0,0],Qp=1200,Qs=600
                vp=data[i-1,1]
                vs=data[i-1,2]
                rho=data[i-1,3]
                if data.shape[1] == 6:
                    Qp=data[i-1,4]
                    Qs=data[i-1,5]
                else:
                    Qp= 1200
                    Qs=600
                Qp *= QMul
                Qs *= QMul
                z =np.array([data[i-1,0],data[min(i+1-1,layerN-2),0]])
                if isFlat and doFlat:
                    z,vp,vs,rho = flat(z,vp,vs,rho,m=flatM,R=R)
                layerL[i] = layer(vp,vs,rho,z,Qp,Qs)
        surfaceL = [None for i in range(layerN-1)]
        for i in range(layerN-1):
            isTop = False
            isBottom = False
            if i == 0:
                isTop = True
            if i == layerN-2:
                isBottom = True
            surfaceL[i] = surface(layerL[i], layerL[i+1], mode, isTop, isBottom)
        self.layerL = layerL
        self.surfaceL = surfaceL
        self.layerN = layerN
    @jit
    def set(self, k,omega):
        for s in self.surfaceL:
            s.setTR(k,omega)
        for i in range(self.layerN-1-1,-1,-1):
            #print(i)
            s = self.surfaceL[i]
            if i == self.layerN-1-1:
                s.setTTRRD(self.surfaceL[0])
            else:
                s.setTTRRD(self.surfaceL[i+1])
        for i in range(self.layerN-1):
            #print(i)
            s = self.surfaceL[i]
            if i == 0:
                s.setTTRRU(self.surfaceL[0])
            else:
                s.setTTRRU(self.surfaceL[i-1])
    @jit
    def get(self, k, omega):
        self.set(k, omega)
        RRud0 = self.surfaceL[0].RRud
        RRdu1 = self.surfaceL[1].RRdu
        if self.getMode == 'norm':
            M = np.mat(np.eye(RRud0.shape[0])) - RRud0*RRdu1
        elif self.getMode == 'new':
            #-E1[1][0]**(-1)*E1[1][1]*(A1[1][1])
            #-E1[1][0]**(-1)*E1[1][1]*(A1[1][1])
            M = np.mat(self.surfaceL[0].E[1][1][0])+np.mat(self.surfaceL[0].E[1][1][1])*np.mat(self.surfaceL[0].A[1][1][1])*RRdu1
            #M = self.surfaceL[0].E[1][1][0]+self.surfaceL[1].E[1][1][1]*self.surfaceL[1].A[1][1][1]*RRdu1
            MA = np.array(M)
            MA /= np.abs(MA).std()
            return np.linalg.det(np.mat(MA))
        return np.linalg.det(M)
    @jit
    def plot(self, omega, dv=0.01):
        #k = np.arange(0,1,dk)
        v, k ,det = self.calList(omega, dv)
        plt.plot(v,np.real(det),'-k')
        plt.plot(v,np.imag(det),'-.k')
        plt.plot(v,np.abs(det),'r')
        plt.show()
    @jit
    def calList(self,omega,dv=0.01):
        vs0 = self.layerL[1].vs
        vp0 = self.layerL[1].vp
        v = np.arange(vs0-0.499,vs0+5,dv)
        k = omega/v
        det = k.astype(np.complex)*0
        for i in range(k.shape[0]):
            det[i] = self.get(k[i], omega)
        return v, k, det
    @jit
    def __call__(self,omega,calMode='fast'):
        return self.calV(omega,order = 0, dv=0.002, DV = 0.008,calMode=calMode,threshold=0.1)
    def calV(self, omega,order = 0, dv=0.001, DV = 0.008,calMode='norm',threshold=0.05,vStart = -1):
        if calMode =='norm':
            v, k ,det = self.calList(omega, dv)
            iL, detL = getDetec(-np.abs(det), minValue=-0.1, minDelta=int(DV /dv))
            i0 = iL[order]
            v0 = v[i0]
            det0 = -detL[0]
        elif calMode == 'fast':
             v0,det0=self.calVFast(omega,order=order,dv=dv,DV=DV,threshold=threshold,vStart=vStart)
        '''
        ddv = 0.001  
        for i in range(5):
            step = 1e-3*(5-i)
            v1 = v0 + ddv
            det1 = np.abs(self.get(omega/v1, omega))
            k = (det1-det0)/ddv
            v0 = v0 - k*step
            print(k)
            det0 = np.abs(self.get(omega/v1, omega))
        '''
        return v0,det0
    @jit
    def calVFast(self,omega,order=0,dv=0.01,DV=0.008,threshold=0.05,vStart=-1):
        if self.getMode == 'new':
            v = 2.7
        else:
            v = self.layerL[1].vs+1e-8

        #print(vStart,v)
        if vStart >0:
            v  = vStart - 0.02
            dv = 0.0005
        v0 = v
        det0=1e9
        for i in range(100000):
            v1 = i*dv+v
            if np.abs(v1-self.layerL[1].vs)<0.005:
                continue
            #print(v1)
            det1 =np.abs(self.get(omega/v1, omega))

            #if i%10:
            #    #print(v1, det1)
            if  det1<threshold and det1 < det0:
                v0 = v1
                det0 = det1
            if det0 <threshold and det1>det0:
                print(v0,2*np.pi/omega,det0)
                return v0, det0
        return 2,0.1
    def calByGpdc(self,order=0,pog='p',T= np.arange(1,100,5).astype(np.float)):
        pogStr=pog
        if pog =='p':
            pog=''
        else:
            pog ='-group'
        modelInPut = self.modelFile+'_gpdc'+'_'+pogStr
        resFile = self.modelFile+'_gpdc_tmp'+'_'+pogStr
        with open(modelInPut,'w') as f:
            count=0
            for layer in self.layerL[1:]:
                if (layer.z[1]-layer.z[0])<0.1:
                    continue

                count+=1
            f.write('%d'%(count))
            for layer in self.layerL[1:]:
                if (layer.z[1]-layer.z[0])<0.1:
                    continue
                f.write('\n')
                f.write('%f %f %f %f'%((layer.z[1]-layer.z[0])*1e3,\
                    layer.vp*1e3,layer.vs*1e3,layer.rho*1e3))
        if self.mode == 'PSV':
            cmdRL = ' -R %d '%(order+1)
        else:
            cmdRL = ' -R 0 -L %d '%(order+1)
            #gpdc Test.model -R 0 -L 5
        cmd = '%s  %s %s  %s -min %f -max %f > %s'%\
        (self.gpdcExe, modelInPut,cmdRL,pog,1/T.max(),1/T.min(),resFile)
        os.system(cmd)
        #print(cmd)
        data = np.loadtxt(resFile)
        return data[:,0],1e-3/data[:,-1]

    @jit
    def calDispersion(self, order=0,calMode='norm',threshold=0.1,T= np.arange(1,100,5).astype(np.float),pog='p'):
        
        if calMode == 'gpdc':
            return self.calByGpdc(order,pog,T)
        f = 1/T
        omega = 2*np.pi*f
        v = omega*0
        v00=3
        for i in range(omega.size):
            if pog =='p':
                V   =np.abs(self.calV(omega[i],order=order,calMode=calMode,threshold=threshold,vStart=v00-0.2))[0]
                v00=V
                v[i]=np.abs(self.calV(omega[i],order=order,calMode=calMode,threshold=threshold,vStart=v00))[0]
            elif pog =='g' :
                omega0 = omega[i]*0.98
                omega1 = omega[i]*1.02
                V=np.abs(self.calV(omega1,order=order,calMode=calMode,threshold=threshold,vStart=v00-0.2))[0]
                v00 = V
                v0=np.abs(self.calV(omega0,order=order,calMode=calMode,threshold=threshold,vStart=v00))[0]
                v1=np.abs(self.calV(omega1,order=order,calMode=calMode,threshold=threshold,vStart=v00))[0]
                
                dOmega = omega1 - omega0
                dK     = omega1/v1 - omega0/v0
                v[i] = dOmega/dK 
            #print(omega[i],v[i])
        return f,v
    def test(self):
        self.plot(2*np.pi)
    def testDispersion(self):
        f,v = self.calDispersion()
        plt.plot(f,v)
        plt.show()
    def compare(self,dv=0.01):
        self.getMode = 'norm'
        v, k ,det = self.calList(6.28, dv)
        plt.plot(v,np.abs(det)/np.abs(det).max(),'k')
        self.getMode = 'new'
        v, k ,det = self.calList(6.28, dv)
        plt.plot(v,np.abs(det)/np.abs(det).max(),'r')
        plt.show()
    def covert2Fk(self, fkMode=0):
        if fkMode == 0:
            filename = self.modelFile+'fk0'
        else:
            filename = self.modelFile+'fk1'
        if self.isFlat:
            filename+='_flat'
        with open(filename,'w+') as f:
            for i in range(1,self.layerN):
                layer = self.layerL[i]
                thickness = layer.z[1] - layer.z[0]
                vp = layer.vp.copy()
                vs = layer.vs.copy()
                rho = layer.rho
                if fkMode == 0:
                    vp/=vs
                print('%.2f %.2f %.2f %.2f %d %d'%(thickness, vs, vp, rho,layer.Qp,layer.Qs))
                f.write('%.2f %.2f %.2f %.2f %d %d'%(thickness, vs, vp, rho,layer.Qp,layer.Qs))
                if i!= self.layerN-1:
                    f.write('\n')
    def outputZV(self):
        layerN = len(self.layerL)
        z  = np.zeros(layerN*2-2)
        vp = np.zeros(layerN*2-2)
        vs = np.zeros(layerN*2-2)
        for i in range(1,layerN):
            iNew = i-1
            z[iNew*2:iNew*2+2] = self.layerL[i].z
            vp[iNew*2:iNew*2+2] =np.array([self.layerL[i].vp,self.layerL[i].vp])
            vs[iNew*2:iNew*2+2] = np.array([self.layerL[i].vs,self.layerL[i].vs])
        return z,vp,vs
    def outputZVRho(self):
        layerN = len(self.layerL)
        z  = np.zeros(layerN*2-2)
        vp = np.zeros(layerN*2-2)
        vs = np.zeros(layerN*2-2)
        rho = np.zeros(layerN*2-2)
        for i in range(1,layerN):
            iNew = i-1
            z[iNew*2:iNew*2+2] = self.layerL[i].z
            vp[iNew*2:iNew*2+2] =np.array([self.layerL[i].vp,self.layerL[i].vp])
            vs[iNew*2:iNew*2+2] = np.array([self.layerL[i].vs,self.layerL[i].vs])
            rho[iNew*2:iNew*2+2] = np.array([self.layerL[i].rho,self.layerL[i].rho])
        return z,vp,vs,rho
    def __call__(self,z):
        z0,vp0,vs0,rho0=self.outputZVRho()
        interpP=interpolate.interp1d(z0,vp0,kind='linear',\
            bounds_error=False,fill_value=vp0[-1])
        interpS=interpolate.interp1d(z0,vs0,kind='linear',\
            bounds_error=False,fill_value=vs0[-1])
        interpRho=interpolate.interp1d(z0,rho0,kind='linear',\
            bounds_error=False,fill_value=rho0[-1])
        return interpP(z),interpS(z),interpRho(z)
    def to2D(self,x,z):
        nz = z.size
        nx = x.size
        zM = np.zeros([nz,nx])+z.reshape([-1,1])
        return self(zM)





class disp:
    '''
    traditional method to calculate the dispersion curve
    then should add some sac to handle time difference
    '''
    def __init__(self,nperseg=300,noverlap=298,fs=1,halfDt=150,xcorrFunc = xcorrComplex):
        self.nperseg=nperseg
        self.noverlap=noverlap
        self.fs = fs
        self.halfDt = halfDt
        self.halfN = np.int(halfDt*self.fs)
        self.xcorrFunc = xcorrFunc
    @jit
    def cut(self,data):
        maxI = np.argmax(data)
        i0 = max(maxI - self.halfN,0)
        i1 = min(maxI + self.halfN,data.shape[0])
        #print(i0,i1)
        return data[i0:i1],i0,i1
    @jit
    def xcorr(self,data0, data1,isCut=True):
        if isCut:
            data1,i0,i1 = self.cut(data1)
        #print(data0.shape,data1.shape1)
        i0=0
        i1=0
        xx = self.xcorrFunc(data0,data1)
        return xx,i0,i1
    @jit
    def stft(self,data):
        F,t,zxx = scipy.signal.stft(np.real(data),fs=self.fs,nperseg=self.nperseg,\
            noverlap=self.noverlap)
        F,t,zxxj = scipy.signal.stft(np.imag(data),fs=self.fs,nperseg=self.nperseg,\
            noverlap=self.noverlap)
        zxx = zxx+zxxj*1j
        zxx /= np.abs(zxx).max(axis=1,keepdims=True)
        return F,t,zxx
    def show(self,F,t,zxx,data,timeL,isShow=True):
        plt.subplot(2,1,1);plt.pcolor(t,F,np.abs(zxx));plt.subplot(2,1,2);plt.plot(timeL,data);
        if isShow:
            plt.show()
    def sacXcorr(self,sac0,sac1,isCut=False):
        fs = sac0.stats['sampling_rate']
        self.fs=fs
        self.halfN = np.int(self.halfDt*self.fs)
        data0 = sac0.data
        time0 = sac0.stats.starttime.timestamp
        dis0  = sac0.stats['sac']['dist']
        data1 = sac1.data
        time1 = sac1.stats.starttime.timestamp
        dis1  = sac1.stats['sac']['dist']
        xx,i0,i1 = self.xcorr(data0,data1,isCut)
        time1New = time1+i0/fs
        dTime =  time0 -time1New
        timeL = np.arange(xx.size)/fs+dTime
        dDis = dis0 - dis1
        #print(np.imag(xx))
        return corr(xx,timeL,dDis,fs)
    def test(self,data0,data1,isCut=True):
        xx = self.xcorr(data0,data1,isCut=isCut)
        F,t,zxx = self.stft(xx)
        self.show(F,t,zxx,xx)
    def testSac(self,sac0,sac1,isCut=True,fTheor=[],vTheor=[]):
        xx,timeL,dDis,fs = self.sacXcorr(sac0,sac1,isCut=True).output()
        F,t,zxx = self.stft(xx)
        print(t)
        t = t+timeL[0]+0*self.nperseg/self.fs
        self.show(F,t,zxx,xx,timeL,isShow=False)
        if len(fTheor)>0:
            timeTheorL =dDis/vTheor
            plt.subplot(2,1,1);plt.plot(timeTheorL,fTheor)
        return xx, zxx, F, t

class fv:
    '''
    class for dispersion result
    it have two attributes f and v, each element in v accosiate with an 
     element in v 
    '''
    def __init__(self,input,mode='num',threshold=0.06):
        if mode == 'num':
            self.f = input[0]
            self.v = input[1]
        if mode == 'file':
            fvM = np.loadtxt(input)
            self.f = fvM[:,0]
            self.v = fvM[:,1]
        if mode == 'NEFile':
            T = []
            v = []
            std =[]
            with open(input) as f:
                lines = f.readlines()
            for line in lines[3:]:
                tmp = line.split()
                T.append(float(tmp[0]))
                v.append(float(tmp[1]))
                std.append(float(tmp[2]))
            f = 1/np.array(T)
            v = np.array(v)
            std = np.array(std)
            f = f[std<threshold]
            v = v[std<threshold]
            if len(f) <=1:
                f = np.array([-1,0])
                v = np.array([-1,0])
            self.f = f 
            self.v = v
        self.interp = self.genInterp()
    def genInterp(self):
        return interpolate.interp1d(self.f,self.v,kind='linear',\
            bounds_error=False,fill_value=1e-8)
    def __call__(self,f,threshold=0.1):
        shape0 =f.shape
        f = f.reshape([-1])   
        vL =  self.interp(f)
        #print((np.abs(f.reshape([-1,1])- self.f.reshape([1,-1]))).min(axis=1).shape)
        dfR = (np.abs(f.reshape([-1,1])- self.f.reshape([1,-1]))).min(axis=1)/f
        vL[dfR>threshold]=vL[dfR>threshold]*0+1e-8
        return vL.reshape(shape0)
    def save(self,filename):
        np.savetxt(filename, np.concatenate([self.f.reshape([-1,1]),\
            self.v.reshape([-1,1])],axis=1))

def getFVFromPairFile(file,fvD={},quakeD={}):
    with open(file) as f :
        lines = f.readlines()
    stat='next'
    for line in lines:
        print(stat)
        if stat=='next':
            sta0 = line.split()[0]
            sta1 = line.split()[1]
            stat = 'comp0'
            continue
        if stat=='comp0':
            stat ='quakeTime0'
            continue
        if stat =='quakeTime0':
            timeL =[int(tmp) for tmp in line.split()[:-1]]
            timeL.append(float(line.split()[-1]))
            time = obspy.UTCDateTime(*timeL)
            stat='sta1Loc'
            continue
        if stat=='sta1Loc':
            stat='QuakeInfo0'
            continue
        if stat=='QuakeInfo0':
            la = float(line.split()[0])
            lo = float(line.split()[1])
            dep= float(line.split()[2])
            ml = float(line.split()[3])
            stat='deltaLoc0'
            continue
        if stat=='deltaLoc0':
            stat='comp1'
            continue
        if stat=='comp1':
            stat ='quakeTime1'
            continue
        if stat =='quakeTime1':
            stat='sta0Loc'
            continue
        if stat=='sta0Loc':
            stat='QuakeInfo1'
            continue
        if stat=='QuakeInfo1':
            stat='deltaLoc1'
            continue
        if stat=='deltaLoc1':
            stat='fNum'
            continue
        if stat== 'fNum':
            fNum = int(line.split()[1])
            f = np.zeros(fNum)
            v = np.zeros(fNum)
            stat= 'f'
            i =0
            continue
        if stat=='f':
            f[i]=float(line)
            i+=1
            if i ==fNum:
                stat='v'
                i=0
                continue
        if stat=='v':
            v[i]=float(line)
            i+=1
            if i ==fNum:
                quake = seism.Quake(time=time,la=la,lo=lo,dep=dep,ml=ml)
                name = quake.name('_')
                if name not in quakeD:
                    quakeD[name]=quake
                key='%s_%s_%s'%(name,sta0,sta1)
                fvD[key]=fv([f,v])
                stat='next'
                continue




class corr:
    """docstring for """
    def __init__(self,xx=np.arange(0,dtype=np.complex),timeL=np.arange(0),dDis=0,fs=0,\
        az=np.array([0,0]),dura=0,M=np.array([0,0,0,0,0,0,0]),dis=np.array([0,0]),\
        dep = 10,modelFile='',name0='',name1='',srcSac='',x0=np.arange(0),\
        x1=np.arange(0)):
        self.maxCount = -1
        maxCount   = xx.shape[0]
        self.dtype = self.getDtype(maxCount)
        self.xx    = xx.astype(np.complex64)
        self.timeL = timeL.astype(np.float32)
        self.dDis  = dDis
        self.fs    = fs
        self.az    = az
        self.dura  = dura
        self.M     = M
        self.dis   = dis
        self.dep   = dep
        self.modelFile=modelFile
        self.name0 = name0
        self.name1 = name1
        self.srcSac= srcSac
        self.x0 = x1.astype(np.float32)
        self.x0 = x1.astype(np.float32)
    def output(self):
        return self.xx,self.timeL,self.dDis,self.fs
    def toDict(self):
        return {'xx':self.xx, 'timeL':self.timeL, 'dDis':self.dDis, 'fs':self.fs,\
        'az':self.az, 'dura':self.dura,'M':self.M,'dis':self.dis,'dep':self.dep,\
        'modelFile':self.modelFile,'name0':self.name0,'name1':self.name1,\
        'srcSac':self.srcSac,'x0':self.x0,'x1':self.x1}
    def toMat(self):
        self.getDtype(self.xx.shape[0])
        return np.array((self.xx, self.timeL, self.dDis,self.fs,self.az, self.dura\
            ,self.M,self.dis,self.dep,self.modelFile,self.name0,self.name1,\
            self.srcSac,self.x0,self.x1),self.dtype)
    def setFromFile(self,file):
        mat        = scipy.io.load(file)
        self.setFromDict(mat)
    def setFromDict(self,mat,isFile =False):
        if not isFile:
            self.xx        = mat['xx']
            self.timeL     = mat['timeL']
            self.dDis      = mat['dDis']
            self.fs        = mat['fs']
            self.az        = mat['az']
            self.dura      = mat['dura']
            self.M         = mat['M']
            self.dis       = mat['dis']
            self.dep       = mat['dep']
            self.modelFile = str(mat['modelFile'])
            self.name0     = str(mat['name0'])
            self.name1     = str(mat['name1'])
            self.srcSac    = str(mat['srcSac'])
            self.x0        = mat['x0']
            self.x1        = mat['x1']
        else:
            self.xx        = mat['xx'][0][0][0]
            self.timeL     = mat['timeL'][0][0][0]
            self.dDis      = mat['dDis'][0][0][0]
            self.fs        = mat['fs'][0][0][0]
            self.az        = mat['az'][0][0][0] 
            self.dura      = mat['dura'][0][0][0] 
            self.M         = mat['M'][0][0][0] 
            self.dis       = mat['dis'][0][0][0]
            self.dep       = mat['dep'][0][0][0]
            self.modelFile = str(mat['modelFile'][0][0][0])
            self.name0     = str(mat['name0'][0][0][0])
            self.name1     = str(mat['name1'][0][0][0])
            self.srcSac    = str(mat['srcSac'][0][0][0])
            self.x0        = mat['x0'][0][0][0]
            self.x1        = mat['x1'][0][0][0]
        return self
    def save(self,fileName):
        sio.savemat(fileName,self.toMat())
    def show(self,d,FV):
        linewidth=0.3
        F,t,zxx = d.stft(self.xx)
        t = t+self.timeL[0]
        ylim=[0,0.2]
        xlim = [t[0],t[-1]]
        ax=plt.subplot(3,2,1)
        plt.plot(self.timeL,np.real(self.xx),'b',linewidth=linewidth)
        plt.plot(self.timeL,np.imag(self.xx),'r',linewidth=linewidth)
        plt.xlabel('t/s')
        plt.ylabel('corr')
        plt.xlim(xlim)
        ax=plt.subplot(3,2,3)
        plt.pcolor(t,F,np.abs(zxx))
        fTheor     = FV.f
        timeTheorL = self.dDis/FV.v
        #print(timeTheorL)
        plt.plot(timeTheorL,fTheor,'r')
        plt.xlabel('t/s')
        plt.ylabel('f/Hz')
        plt.xlim(xlim)
        plt.ylim(ylim)
        ax=plt.subplot(3,2,2)
        sac0 = obspy.read(self.name0)[0]
        sac1 = obspy.read(self.name1)[0]
        plt.plot(getSacTimeL(sac0),sac0,'b',linewidth=linewidth)
        plt.plot(getSacTimeL(sac1),sac1,'r',linewidth=linewidth)
        plt.xlabel('time/s')
        ax=plt.subplot(3,2,4)
        mat = np.loadtxt(self.modelFile)
        ax.invert_yaxis() 
        #'0.00       5.800     3.350       2.800    1400.0     600.0'
        plt.plot(mat[:,1],mat[:,0],'b',linewidth=linewidth)
        plt.plot(mat[:,2],mat[:,0],'r',linewidth=linewidth)
        plt.ylim([900,-10])
        plt.subplot(3,2,5)
        timeDis = self.outputTimeDis(FV)
        plt.pcolor(self.timeL,self.T,timeDis.transpose())
    def getDtype(self,maxCount):
        if False :#maxCount == self.maxCount:
            return self.dtype
        else:
            self.maxCount=maxCount
            corrType = np.dtype([ ('xx'       ,np.complex64,maxCount),\
                                  ('timeL'    ,np.float32,maxCount),\
                                  ('dDis'     ,np.float64,1),\
                                  ('fs'       ,np.float64,1),\
                                  ('az'       ,np.float64,2),\
                                  ('dura'     ,np.float64,1),\
                                  ('M'        ,np.float64,7),\
                                  ('dis'      ,np.float64,2),\
                                  ('dep'      ,np.float64,1),\
                                  ('modelFile',np.str,200),\
                                  ('name0'    ,np.str,200),\
                                  ('name1'    ,np.str,200),\
                                  ('srcSac'   ,np.str,200),\
                                  ('x0'    ,np.float32,maxCount),\
                                  ('x1'    ,np.float32,maxCount)
                                  ])
            return corrType
    def outputTimeDis(self,FV,T=np.array([5,10,20,30,50,80,100,150,200,250,300]),sigma=2,\
        byT=False,byA=False,rThreshold=0.1):
        self.T=T
        f  = 1/T
        t0 = self.timeL[0]
        dim = [self.timeL.shape[0],T.shape[0]]
        timeDis = np.zeros(dim)
        f = f.reshape([1,-1])
        timeL = self.timeL.reshape([-1,1])
        v = FV(f)
        t = self.dDis/v
        tmpSigma = sigma
        if byT:
            tMax =max(300,t.max())
            tmpSigma = sigma/300*tMax
        timeDis = np.exp(-((timeL-t)/tmpSigma)**2)
        if byA:
            spec = np.abs(np.fft.fft(self.xx))
            spec/=spec.max()
            minf = 1/(len(self.timeL)*(self.timeL[1]-self.timeL[0]))
            indexF = (f.reshape([-1])/minf).astype(np.int)
            aF = spec[indexF]
            #print(aF,aF<rThreshold)
            timeDis[:,aF<rThreshold]=timeDis[:,aF<rThreshold]*0
        return timeDis,t0
    def compareInOut(self,yin,yout,t0):
        aIn = yin.argmax(axis=0)
        posIn   = yin.argmax(axis=0)/self.fs
        posOut  = yout.argmax(axis=0)/self.fs
        dPos    = posOut - posIn
        dPosR   = dPos/(posIn+t0+1e-8)
        dPos[aIn<0.5] = dPos[aIn<0.5]*0-100000
        dPosR[aIn<0.5] = dPosR[aIn<0.5]*0-10000
        return dPos, dPosR, dPos*0 + self.dDis
    def getV(self,yout):
        posOut = yout.argmax(axis=0).reshape([-1])
        prob = yout.max(axis=0).reshape([-1])
        tOut   = self.timeL[posOut]
        v  = self.dis/tOut
        return v,prob
def compareList(i0,i1):
    di = np.array(i0)-np.array(i1)
    return np.sum(np.abs(di))<0.1

class corrL(list):
    def __init__(self,*argv,**kwargs):
        super().__init__()
        if len(argv)>0:
            for tmp in argv[0]:
                if 'fvD' in kwargs:
                    fvD = kwargs['fvD']
                    modelName =tmp.modelFile
                    if len(modelName.split('_'))>=2:
                        name0 = modelName.split('_')[-2]
                        name1 = modelName.split('_')[-1]
                        modelName0 ='%s_%s'%(name0,name1)
                        modelName1 ='%s_%s'%(name1,name0)
                        if modelName0 not in fvD and modelName1 not in fvD:
                            continue
                self.append(tmp)
        self.iL=np.arange(0)
        self.timeDisArgv = ()
        self.timeDisKwarg={}
            #if isinstance(argv[0],corrL):
            #    self.x=argv[0].x
            #    self.y=argv[0].y
    def plotPickErro(self,yout,T,iL=[],fileName='erro.jpg'):
        plt.close()
        N = yout.shape[0]
        if len(iL) == 0:
            iL = self.iL
        dPosL = np.zeros([N,len(T)])
        dPosRL = np.zeros([N,len(T)])
        fL = np.zeros([N,len(T)])
        dDisL = np.zeros([N,len(T)])
        for i in range(N):
            index   = iL[i]
            tmpCorr = self[index]
            tmpYin  = self.y[i,:,0]
            tmpYOut = yout[i,:,0]
            t0      = self.t0L[i]
            dPos, dPosR,dDis = tmpCorr.compareInOut(tmpYin,tmpYOut,t0)
            f = (1/T)
            dPosL[i,:]  = dPos
            dPosRL[i,:] = dPosR
            fL[i,:]=f
            dDisL[i,:]=dDis
            #print(dPos.shape,dDis.shape)
        bins   = np.arange(-50,50,2)/4
        res    = np.zeros([len(T),len(bins)-1])
        for i in range(len(T)):
            res[i,:],tmp=np.histogram(dPosL[dPosL[:,i]>-1000,i],bins,density=True)
        plt.pcolor(bins[:-1],1/T,res,cmap='bwr')
        #plt.scatter(dPosL,fL,s=0.5,c = dDisL/2000,alpha=0.3)
        plt.xlabel('erro/s')
        plt.ylabel('f/Hz')
        plt.colorbar()
        plt.gca().semilogy()
        plt.gca().invert_yaxis()
        plt.title(fileName[:-4])
        plt.savefig(fileName,dpi=300)
        plt.close()

        bins   = np.arange(-50,50,1)/400
        res    = np.zeros([len(T),len(bins)-1])
        for i in range(len(T)):
            res[i,:],tmp=np.histogram(dPosRL[dPosRL[:,i]>-1000,i],bins,density=True)
        plt.pcolor(bins[:-1],1/T,res,cmap='bwr')
        #plt.scatter(dPosL,fL,s=0.5,c = dDisL/2000,alpha=0.3)
        plt.xlabel('erro Ratio /(s/s)')
        plt.ylabel('f/Hz')
        plt.colorbar()
        plt.gca().semilogy()
        plt.gca().invert_yaxis()
        plt.title(fileName[:-4]+'_R')
        plt.savefig(fileName[:-4]+'_R.jpg',dpi=300)
        plt.close()
    def setTimeDis(self,*argv,**kwargs):
        self.timeDisArgv = argv
        self.timeDisKwarg=kwargs
        self.iL=np.arange(0)
    def __call__(self,iL):
        self.getTimeDis(iL,*self.timeDisArgv,**self.timeDisKwarg)
        return self.x, self.y, self.t0L
    def getTimeDis(self,iL,fvD={},T=[],sigma=2,maxCount=512,noiseMul=0,byT=False,\
        byA=False,rThreshold=0.1,byAverage=False):
        #print('sigma',sigma)
        if len(iL)==0:
            iL=np.arange(len(self))
        if not isinstance(iL,np.ndarray):
            iL = np.array(iL).astype(np.int)
        if iL.size == self.iL.size:
            if compareList(iL,self.iL):
                print('already done')
                return None
        self.iL = iL
        maxCount0 = maxCount
        x      = np.zeros([len(iL),maxCount,1,4])
        y      = np.zeros([len(iL),maxCount,1,len(T)])
        t0L    = np.zeros(len(iL))
        dDisL  = np.zeros(len(iL))
        deltaL = np.zeros(len(iL))
        randIndexL = np.zeros(len(iL))
        for ii in range(len(iL)):
            i = iL[ii]
            maxCount = min(maxCount0,self[i].xx.shape[0],self[i].x0.shape[0],\
                self[i].x1.shape[0])
            modelName =self[i].modelFile
            if byAverage:
                if len(modelName.split('_'))>=2:
                    name0 = modelName.split('_')[-2]
                    name1 = modelName.split('_')[-1]
                    modelName0 ='%s_%s'%(name0,name1)
                    modelName1 ='%s_%s'%(name1,name0)
                    #print(modelName0)
                    if modelName0 in fvD:
                        #print(modelName0)
                        modelName = modelName0
                    if modelName1 in fvD:
                        #print(modelName1)
                        modelName = modelName1
            tmpy,t0=self[i].outputTimeDis(fvD[modelName],\
                T=T,sigma=sigma,byT=byT,byA=byA,rThreshold=rThreshold)
            iP,iN = self.ipin(t0,self[i].fs)
            y[ii,iP:maxCount+iN,0,:] =tmpy[-iN:maxCount-iP]
            x[ii,iP:maxCount+iN,0,0] = np.real(self[i].xx.\
                reshape([-1]))[-iN:maxCount-iP]
            x[ii,iP:maxCount+iN,0,1] = np.imag(self[i].xx.\
                reshape([-1]))[-iN:maxCount-iP]
            dt = np.random.rand()*5-2.5
            iP,iN = self.ipin(t0+dt,self[i].fs)
            x[ii,iP:maxCount+iN,0,2] = self[i].x0.\
            reshape([-1])[-iN:maxCount-iP]
            iP,iN = self.ipin(dt,self[i].fs)
            x[ii,iP:maxCount+iN,0,3]       = self[i].x1.\
            reshape([-1])[-iN:maxCount-iP]
            #print('###',t0,dt,iP,iN)
            t0L[ii]=0
            dDisL[ii] = self[i].dDis
            deltaL[ii]= self[i].timeL[1]-self[i].timeL[0]
        xStd = x.std(axis=1,keepdims=True)
        self.x          = x+noiseMul*np.random.rand(*list(x.shape))*xStd
        self.y          = y
        self.randIndexL = randIndexL
        self.t0L        = t0L
        self.dDisL      = dDisL
        self.deltaL     = deltaL
        #print(x[0,1500,0])
    def getV(self,yout,isSimple=True,D=0.1,isLimit=False):
        if isSimple:
            pos = yout.argmax(axis=1)[:,0]
            prob= yout.max(axis=1)[:,0]
            time= self.t0L.reshape([-1,1])+pos*self.deltaL.reshape([-1,1])
            v   = self.dDisL.reshape([-1,1])/(time)
        else:
            if isLimit:
                yout *= (self.y.max(axis=1,keepdims=True)>0.5)
            N    = yout.shape[0]
            M    = yout.shape[-1]
            v    = np.zeros([N,M])
            prob = np.zeros([N,M])
            fvD = self.timeDisArgv[0]
            T = self.timeDisArgv[1]
            for i in range(N):
                index = self.iL[i]
                modelFile = self[index].modelFile
                fv=fvD[modelFile]
                for j in range(M): 
                    v0 = fv(1/T[j])
                    minV = (1-D)*v0
                    maxV = (1+D)*v0
                    maxT = self.dDisL[i]/minV
                    minT = self.dDisL[i]/maxV
                    i0 = max(0,int((minT - self.t0L[0])/self.deltaL[i]))
                    i1 = min(yout.shape[1]-1,int((maxT - self.t0L[0])/self.deltaL[i]))
                    pos      = yout[i,i0:i1,0,j].argmax()+i0
                    time     = self.t0L[i]+pos*self.deltaL[i]
                    prob[i,j]= yout[i,i0:i1,0,j].max()
                    v[i,j]   = self.dDisL[i]/time
        return v,prob
    def saveV(self,v,prob,f,T,iL=[]):
        if len(iL) ==0:
            iL=self.iL
        for i in range(v.shape[0]):
            index = iL[i]
            corr  = self[index]
            f.write('%s %s %s %s | '%(corr.srcSac, corr.modelFile, corr.name0, corr.name1))
            for tmp in T:
                f.write(' %.3f '% (1/tmp))
            f.write('|')
            for tmp in v[i]:
                f.write(' %.3f '% tmp)
            f.write('|')
            for tmp in prob[i]:
                f.write(' %.3f '% tmp)
            f.write('\n')
    def getAndSave(self,model,fileName,isPlot=False,isSimple=True,D=0.2,isLimit=False):
        N = len(self)
        if 'T' in self.timeDisKwarg:
            T = self.timeDisKwarg['T']
        else:
            T = self.timeDisArgv[1]
        M = len(T)
        v = np.zeros([N,M])
        v0= np.zeros([N,M])
        prob=np.zeros([N,M])
        prob0=np.zeros([N,M])
        for i0 in range(0,N,1000):
            i1 = min(i0+1000,N-1)
            x, y, t= self(np.arange(i0, i1))
            v[i0:i1],prob[i0:i1]=self.getV(model.predict(x),isSimple=isSimple,D=D,isLimit=isLimit)
            v0[i0:i1],prob0[i0:i1]=self.getV(y)
        with open(fileName,'w+') as f:
            self.saveV(v,prob,f,T, np.arange(N))
        if isPlot:
            '''
            plt.close()
            plt.plot(v.transpose(),1/T,'k',linewidth=0.1,alpha=0.3)
            plt.gca().semilogy()
            plt.xlim([2.5,6])
            plt.savefig(fileName+'.jpg',dpi=300)

            plt.close()
            plt.plot(v.transpose()-v0.transpose(),1/T,'k',linewidth=0.1,alpha=0.3)
            plt.gca().semilogy()
            plt.xlim([2.5,6])
            plt.savefig(fileName+'_dv.jpg',dpi=300)
            '''
            dv = np.abs(v-v0)
            plt.close()
            for i in range(dv.shape[0]):
                indexL = validL(dv[i],prob[i],minProb=0.75,minV=-1,maxV=2)
                if np.random.rand()<0.1:
                        print('validL: ',indexL)
                for iL in indexL:
                    iL = np.array(iL).astype(np.int)
                    plt.plot(v[i,iL],1/T[iL],'k',linewidth=0.1,alpha=0.3)
            plt.xlim([2,7])
            plt.gca().semilogy()
            plt.xlabel('v/(m/s)')
            plt.ylabel('f/Hz')
            plt.savefig(fileName+'.jpg',dpi=300)

            for i in range(dv.shape[0]):
                indexL = validL(dv[i],prob[i],minProb=0.75,minV=-1,maxV=2)
                if np.random.rand()<0.1:
                        print('validL: ',indexL)
                for iL in indexL:
                    iL = np.array(iL).astype(np.int)
                    plt.plot(dv[i,iL],1/T[iL],'k',linewidth=0.1,alpha=0.3)
            plt.xlim([2,7])
            plt.xlabel('dv/(m/s)')
            plt.ylabel('f/Hz')
            plt.gca().semilogy()
            plt.savefig(fileName+'_dv.jpg',dpi=300)
            

    def ipin(self,dt,fs):
        i0 = int(dt*fs)
        iP = 0 
        iN = 0
        if i0>0:
            iP=i0
        else:
            iN=i0
        return iP,iN
    def copy(self):
        return corrL(self)



def getSacTimeL(sac):
    return np.arange(len(sac))*sac.stats['delta']+sac.stats['sac']['b']

def corrSac(d,sac0,sac1,name0='',name1='',az=np.array([0,0]),dura=0,M=np.array([0,0,0,0,0,0,0])\
    ,dis=np.array([0,0]),dep = 10,modelFile='',srcSac='',isCut=False):
    corr = d.sacXcorr(sac0,sac1,isCut=isCut)
    corr.az    = az
    corr.dura  = dura
    corr.M     = M
    corr.dis   = dis
    corr.dep   = dep
    corr.modelFile = modelFile
    corr.name0 = name0
    corr.name1 = name1
    corr.srcSac=srcSac
    corr.x0 = sac0.data
    corr.x1 = sac1.data
    return corr

def corrSacsL(d,sacsL,sacNamesL,dura=0,M=np.array([0,0,0,0,0,0,0])\
    ,dep = 10,modelFile='',srcSac='',minSNR=5,isCut=False,\
    maxDist=1e8,minDist=0,maxDDist=1e8,minDDist=0,isFromO = False,\
    removeP=False,isLoadFv=False,fvD={},quakeName=''):
    if removeP:
        print('removeP')
    corrL = []
    N = len(sacsL)
    distL = np.zeros(N)
    SNR = np.zeros(N)
    for i in range(N):
        distL[i] = sacsL[i][0].stats['sac']['dist']
        pos = np.abs(sacsL[i][0].data).argmax()
        dTime = pos*sacsL[i][0].stats['sac']['delta']+sacsL[i][0].stats['sac']['b']
        #print(pos,dTime,distL[i])
        SNR[i] = np.abs(sacsL[i][0].data[pos])/sacsL[i][0].data[:int(pos/4)].std()
        if removeP:

            tStart = distL[i]/5
            t0 = max(1,tStart-50+5*(np.random.rand()-0.5))
            dt0 = t0 - sacsL[i][0].stats['sac']['b']
            i0 = max(0,int(dt0/sacsL[i][0].stats['sac']['delta']))

            tEnd = distL[i]/2.5
            t1 = max(1,tEnd+100+5*(np.random.rand()-0.5))
            dt1 = t1 - sacsL[i][0].stats['sac']['b']
            i1 = min(sacsL[i][0].data.size,int(dt1/sacsL[i][0].stats['sac']['delta']))
            sacsL[i][0].data[:i0]*=0
            sacsL[i][0].data[i1:]*=0
    #print(SNR)
    print((SNR>minSNR).sum(),minSNR,isLoadFv,len(fvD))
    iL = distL.argsort()
    for ii in range(N):
        for jj in range(ii):
            i = iL[ii]
            j = iL[jj]
            sac0    = sacsL[i][0]
            sac1    = sacsL[j][0]
            name0   = sacNamesL[i][0]
            name1   = sacNamesL[j][0]
            if SNR[i]<minSNR:
                continue
            if SNR[j]<minSNR:
                continue
            #print(sac0,sac1,sac0.stats['sac']['az'],sac1.stats['sac']['az'])
            az   = np.array([sac0.stats['sac']['az'],sac1.stats['sac']['az']])
            if not (isLoadFv and len(quakeName)>0):
                if np.abs((az[0]-az[1])%360)>5:
                    continue

            dis  = np.array([sac0.stats['sac']['dist'],sac1.stats['sac']['dist']])
            
            if dis.min()<minDist:
                continue
            if np.abs(dis[0]-dis[1])<minDDist:
                continue
            if dis.max()>maxDist:
                continue
            if np.abs(dis[0]-dis[1])>maxDDist:
                continue
             
            #tmp = corrSac(d,sac0,sac1,name0,name1,az,dura,M,dis,dep,modelFile)
            #print(np.imag(tmp.xx))
            if isLoadFv:
                modelFile0 = sac0.stats['station']+'_'+sac1.stats['station']
                modelFile1 = sac1.stats['station']+'_'+sac0.stats['station']
                if quakeName!='':
                   modelFile0=quakeName+'_'+modelFile0 
                   modelFile1=quakeName+'_'+modelFile1 
                if modelFile0  in fvD:
                    modelFile = modelFile0
                if modelFile1  in fvD:
                    modelFile = modelFile1
                if modelFile0 not  in fvD and modelFile1 not in fvD:
                    continue
            corrL.append(corrSac(d,sac0,sac1,name0,name1,az,dura,M,dis,dep,modelFile,srcSac,isCut=isCut))
    return corrL        


class fkcorr:
    def __init__(self,config=config()):
        self.config = config
    def __call__(self,index,iL,f,mul=290,depth0=-1,srcSacIndex=0,\
        dura0=-1,rise0=-1,M0=[],azimuth=[0]):
            #print('add',len(corrLL),len(corrLL[index]))
        #print(len(corrLL[index]))
        #return []
        for i in iL:
            if i<0:
                modelFile = '%s'%(self.config.originName)
            else:
                modelFile = '%s%d'%(self.config.originName,i)
            #print(modelFile)
            m = self.config.getModel(modelFile)
            m.covert2Fk(0)
            m.covert2Fk(1)
            if dura0<0:
                dura = np.random.rand()*10+20
            else:
                dura = dura0
            if depth0<0:
                depth= int(np.random.rand()*20+10)+(i%39)
            else:
                depth = depth0
            print('###################################',depth)
            if len(M0)==0:
                M=np.array([3e25,0,0,0,0,0,0])
                M[1:] = np.random.rand(6)
            else:
                M = M0
            if srcSacIndex>=0:
                srcSacIndex = int(np.random.rand()*self.config.srcSacNum*0.999)
            if rise0 <0:
                rise = 0.1+0.3*np.random.rand()
            else:
                rise = rise0
            sacsL, sacNamesL= f.test(distance=self.config.distance+\
                np.round((np.random.rand(self.config.distance.size)-0.5)*mul),\
                modelFile=modelFile,fok=self.config.fok,dt=self.config.delta,\
                depth=depth,expnt=self.config.expnt,dura=dura,\
                dk=self.config.dk,azimuth=azimuth,M=M,rise=rise,\
                srcSac=getSourceSacName(srcSacIndex,self.config.delta,\
                    srcSacDir = self.config.srcSacDir),isFlat=self.config.isFlat)
            #print(len(corrLL[index]),len(dispL) )
            with open(modelFile+'sacFile','w') as ff:
                for sacNames in sacNamesL:
                    for sacName in sacNames:
                        ff.write('%s '%sacName)
                    ff.write('\n')
                ff.write('#')
                ff.write('%s'%(getSourceSacName(srcSacIndex,self.config.delta,srcSacDir = self.config.srcSacDir)))




'''
def singleFk(f,iL,corrLL,index,D,originName,srcSacDir,distance,srcSacNum,delta,layerN):
    for i in iL:
        modelFile = '%s%d'%(originName,i)
        print(modelFile)
        m = model(modelFile=modelFile,mode='PSV',layerN=layerN,layerMode ='prem',isFlat=True)
        m.covert2Fk(0)
        m.covert2Fk(1)
        dura = np.random.rand()*10+20
        depth= int(np.random.rand()*20+10)+(i%10)
        print('###################################',depth)
        M=np.array([3e25,0,0,0,0,0,0])
        M[1:] = np.random.rand(6)
        srcSacIndex = int(np.random.rand()*srcSacNum*0.999)
        rise = 0.1+0.3*np.random.rand()
        sacsL, sacNamesL= f.test(distance=distance+np.round((np.random.rand(distance.size)-0.5)*80),\
            modelFile=modelFile,fok='/k',dt=delta,depth=depth,expnt=10,dura=dura,dk=0.1,\
            azimuth=[0,int(6*(np.random.rand()-0.5))],M=M,rise=rise,srcSac=getSourceSacName(srcSacIndex,delta,\
                srcSacDir = srcSacDir),isFlat=True)
        corrLL[index] += corrSacsL(D,sacsL,sacNamesL,modelFile=modelFile,\
            srcSac=getSourceSacName(srcSacIndex,delta,srcSacDir = srcSacDir))
#           20,d.singleFk,20,D,'models/ak135',srcSacDir,distance,srcSacNum,delta,orignExe=orignExe
'''
'''
def multFK(FKCORR,fkN,num,orignExe):
    fkN = 20 
    fkL = FKL(fkN,orignExe=orignExe)
    pL = []
    manager = Manager()
    corrLL  = manager.list()
    for i in range(fkN):
        corrLL. append([])
    for i in range(fkN):
        f = fkL[i]
        pL.append(Process(\
            target=FKCORR,\
            args=(f,range(i,num,fkN), corrLL,i) 
            )\
        )
        pL[-1].start()
    for p in pL:
        p.join()
        print('######',i)
        i+=1
    corrL = []
    for tmp in corrLL:
        corrL += tmp
        corrMat = np.array(corrL)
    return corrMat
'''
'''
def genFvFile(modelFile,fvFile='',mode='PSV',getMode = 'norm',layerMode ='prem',layerN=20,calMode='fast',\
    T=np.array([0.5,1,5,10,20,30,50,80,100,150,200,250,300]),isFlat=False,pog='p'):
    if len(fvFile) ==0:
        if not isFlat:
            fvFile='%s_fv'%modelFile
        else:
            fvFile='%s_fv_flat'%modelFile
        fvFile+= '_'+getMode
        fvFile+= '_'+pog
    m = model(modelFile,mode=mode,getMode=getMode,layerMode=layerMode,layerN=layerN,isFlat=isFlat)
    f,v=m.calDispersion(order=0,calMode=calMode,threshold=0.1,T=T,pog=pog)
    f = fv([f,v],'num')
    f.save(fvFile)

def calFv(iL,originName='models/prem',layerN=20,pog='p',\
    T=np.array([5,10,20,30,50,80,100,150,200,250,300])):
    for i in iL:
        modelFile = '%s%d'%(originName,i)
        print(i)
        genFvFile(modelFile,fvFile='',mode='PSV',getMode = 'norm',layerMode ='prem',layerN=layerN,calMode='fast',\
            T=T,isFlat=True,pog=pog)
'''
