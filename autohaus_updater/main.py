import requests
import argparse
import git
import os
import sys
import subprocess
import flask
from enum import Enum
from threading import Thread
import urllib.parse
import time
import json
import autohaus_updater

def is_git_repo(path):
    try:
        _ = git.Repo(path).git_dir
        return True
    except git.exc.InvalidGitRepositoryError:
        return False

parser = argparse.ArgumentParser(description='Autohaus update server')
parser.add_argument('--repo_wdir', type=str, required=True)
parser.add_argument('--gitUrl', type=str, default="git@github.com:Coimbra1984/autohaus.git")
parser.add_argument('--gitRemoteOrigin', type=str, default="origin")
parser.add_argument('-f', action='store_true')
parser.add_argument('--updateServerPort', type=int, default=5000)
parser.add_argument('--updateServerBaseURL', type=str, default="/autohaus-update/api/v1.0/")
parser.add_argument('--updateServerHost', type=str, default="127.0.0.1")
parser.add_argument('--mainServerPort', type=int, default=5001)
parser.add_argument('--mainServerHost', type=str, default="127.0.0.1")
parser.add_argument('--pythonExecutable', type=str, default="python")


args = parser.parse_args()

repo_wdir = args.repo_wdir

print("check if %s exists..."%repo_wdir)
folderExists = os.path.exists(repo_wdir)
if folderExists == False:
    print("path doesn't exist, try to create it...")
    os.makedirs(repo_wdir, exist_ok=True)
    print("...ok")
else:
    empty = False
    if len(os.listdir(repo_wdir)) == 0:
        empty = True
    else:
        print("...path is not empty, check if it is already our remote repo")
        if is_git_repo(repo_wdir) == False:
            sys.exit('Path %s exists, is not empty and no git repository'%repo_wdir)
        else:
            repo = git.Repo(repo_wdir)        
            if args.gitUrl in list(repo.remotes[args.gitRemoteOrigin].urls):
                print("...repo points to %s, this is ok"%(args.gitUrl))
                
                print ("check if repo is dirty...")
                if repo.is_dirty() and args.f == False:
                    sys.exit("Repo in path %s is dirty, stopping..."%(repo_wdir))
                print ("...ok")
            else:
                sys.exit("Repo in path %s doesn't point to %s"%(repo_wdir, args.gitUrl))

if empty:
    print("cloning %s into %s"%(args.gitUrl, repo_wdir))
    git.Repo.clone_from(args.gitUrl, repo_wdir)
    print("...done")
    repo = git.Repo(repo_wdir)        

tagName = next((tag for tag in repo.tags if tag.commit == repo.head.commit), None)
if tagName != None:
    print("running on tagged version %s"%str(tagName))
else:
    print("UNTAGGED local version, current commit of repo is %s"%(repo.head.object.hexsha))

print("installing autohaus from local repo...")
retval = subprocess.run([args.pythonExecutable, '-m', 'pip', 'install', '.'], stdout=subprocess.PIPE, cwd=repo_wdir)
if retval.returncode != 0:
    sys.exit("error installing autohaus")

print("...ok")

def startAutohaus(args, timeout=30):
    print("starting autohaus-server")
    proc = subprocess.Popen([args.pythonExecutable, "-m", "autohaus.main", "--port", str(args.mainServerPort), "--host", str(args.mainServerHost)])
    print("...waiting")
    
    started = time.time()
    while True:
        url = "http://%s:%d/autohaus/api/v1.0/version"%(args.mainServerHost, args.mainServerPort)
        print ("trying to access autohaus rest-api at %s"%url)
        try:
            resp = requests.get(url)
            if resp.status_code == 200:
                version = json.loads(resp.content)["version"]
                print("autohaus-server version is %s"%version)
                break
        except Exception as e: 
            print(e)
        
        if time.time() - started > timeout:
            raise RuntimeError("could not connect to %s within %d seconds"%(url, timeout))
        print ("retry in 3 seconds...")
        time.sleep(3)
    
    return proc

def stopAutohaus(args, timeout:int=30):
    ok = False
    url = "http://%s:%d/autohaus/api/v1.0/stop"%(args.mainServerHost, args.mainServerPort)
    resp = requests.post(url)
    if resp.status_code == 200:
        ok = True
        start = time.time()
        while True:
            print("waiting for server shutdown...")
            try:
                resp = requests.post(url)
                print("... still no shutdown")
                time.sleep(1)
            except:
                break
            if time.time() -start > timeout:
                print("timeout waiting for shutdown")
                return False
    else:
        print("server returned %d"%(resp.status_code))
    return ok

startAutohaus(args)

#%%
class UpdateState(Enum):
    IDLE = 0
    GIT_UPDATE = 1
    PIP_UPDATE = 2
    MODULE_RELOAD = 3

class UpdateError(Enum):
    GIT_ERROR = 0
    ALREADY_UPDATING = 1
    PIP_ERROR = 2
    RELOAD_ERROR = 3

class Err:
    def __init__(self):
        self.err = ""
        
    def clear(self):
        self.err = ""
    
    def setError(self, error: str):
        self.err = error
        
    def getError(self) -> str:
        return self.err

class UpdateException(Exception):
    def __init__(self, message: str, error: UpdateError):
        super().__init__(message)
        self.error = error

class Updater:
    def __init__(self, repo: git.Repo, args, restartTimeout:int = 30):
        self.repo = repo
        self.state = UpdateState.IDLE
        self.err = Err()
        self.updateThread = None
        self.args = args
        self.restartTimeout = restartTimeout

    def performUpdate(self, version: str):
        self.err.clear()
        print("checking out git version %s..."%version)
        try:
            self.repo.git.checkout(version)
        except:
            self.err.setError("git update error")
            self.state = UpdateState.IDLE
            raise UpdateException("git error", UpdateError.GIT_ERROR)
        print("...ok")

        print("performing pip update...")
        self.state = UpdateState.PIP_UPDATE
        retval = subprocess.run([args.pythonExecutable, '-m', 'pip', 'install', '.'], stdout=subprocess.PIPE, cwd=repo_wdir)
        if retval.returncode != 0:
            self.err.setError("pip error")
            self.state = UpdateState.IDLE
            raise UpdateException("pip error", UpdateError.PIP_ERROR)
        
        print (retval.stdout)
        print("...ok")
        
        self._reload()
            
    def _reload(self):
        self.state = UpdateState.MODULE_RELOAD
        print("reloading python module...")
        try:
            stopAutohaus(self.args)
            print("...ok")
        except Exception as e:
            print("...error stopping autohaus-server: %s"%str(e))
            print("continue anyway...")
        
        print("trying to start autohaus-server...")
        
        try:
            startAutohaus(self.args, self.restartTimeout)
            print("...ok")
        except:
            self.err.setError("reload error")
            raise UpdateException("reload error", UpdateError.RELOAD_ERROR)
        finally:
            self.state = UpdateState.IDLE

    def reload(self):
        if self.state != UpdateState.IDLE:
            raise UpdateException("update in progress", UpdateError.ALREADY_UPDATING)
        self.err.clear()
        self._reload()

    def update(self, version: str):
        if self.state != UpdateState.IDLE:
            raise UpdateException("update already in progress", UpdateError.ALREADY_UPDATING)
        
        self.state = UpdateState.GIT_UPDATE
        self.updateThread = Thread(target=self.performUpdate, args=(version,))
        self.updateThread.start()


updater = Updater(repo, args)

#%%
app = flask.Flask("autohaus-update-server")
@app.route(urllib.parse.urljoin(args.updateServerBaseURL, 'version'), methods=['GET', 'POST'])
def version():
    if flask.request.method == "GET":
        return flask.jsonify({"version": autohaus_updater.__version__}), 200
    else:
        data = flask.request.get_json()
        if not data:
            return flask.jsonify({"message": "Must provide a version field"}), 400
        if "version" not in data:
            return flask.jsonify({"message": "Must provide a version field"}), 400
        version = data["version"]
        try:
            updater.update(version)
        except UpdateException:
            return flask.jsonify({"message": "Update already in progress"}), 409

        return flask.jsonify({"success": True}), 200

@app.route(urllib.parse.urljoin(args.updateServerBaseURL, 'state'), methods=['GET'])
def state():
    return flask.jsonify({"state": updater.state.name, "value": updater.state.value}), 200

@app.route(urllib.parse.urljoin(args.updateServerBaseURL, 'reload'), methods=['POST'])
def reload():
    try:
        updater.reload()
    except UpdateException:
        return flask.jsonify({"message": "Update in progress"}), 409
    return flask.jsonify({"success": True}), 200

@app.route(urllib.parse.urljoin(args.updateServerBaseURL, 'error'), methods=['GET'])
def error():
    return flask.jsonify({"lastError": updater.err.getError()}), 200


if __name__ == '__main__':
    app.run(debug=False, threaded=False, port=args.updateServerPort, host=args.updateServerHost)