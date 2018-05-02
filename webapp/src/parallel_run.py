import torch
import multiprocessing as mp
import os
import time
import numpy as np
import threading

def iterable(a):
    try:
        iter(a)
        return True
    except:
        return False
    
def map_parallel(f, tasks):
    ''' 
    embrassingly parallel
    f: function to apply
    tasks: list of argument lists
    '''
    n_cpus = min(int(multiprocessing.cpu_count() / 2), len(tasks))

    result_list = []
    pool = multiprocessing.Pool(n_cpus)
    for task in tasks:
        if not iterable(task):
            task = (task,)
        result_list.append(pool.apply_async(func=f, 
                                            args=task))
    while True:
        try:
            def call_if_ready(result):
                if result.ready():
                    result.get()
                    return True
                else:
                    return False    
            done_list = list(map(call_if_ready, result_list))
            print('{}/{} done'.format(sum(done_list), len(result_list)))
            if np.all(done_list):
                break
            time.sleep(3)
        except:
            pool.terminate()
            raise
    print('finished preprocessing')

    return [r.get() for r in result_list]

# a data structure containing the following functionalities
# 1) add task (done)
# 2) delete task (done)
# 3) show progress (done)

class ProcessManager():
    def __init__(self, max_size=3):
        self.max_size = max_size
        self.ps_run = [] # currently running
        self.ps_done = set() # finished running
        self.ps_wait = [] # in the waiting list
        self.manager = mp.Manager()
        self.return_dict = self.manager.dict()
        self.process_key = 0 # key is for retrieval of result
        self.run_thread = None
        
        # locks for ps_run, ps_done, ps_wait
        self.ps_lock = threading.Lock()
        
    
    def _decorate_return(self, target, key):
        '''decorate functions so that result are saved in return_dict'''
        def _f(*args):
            res = target(*args)
            self.return_dict[key] = res 
        return _f

    def ready(self):
        self.ps_lock.acquire()
        # all done
        total = len(self.ps_done) + sum([p.is_alive() for p in self.ps_run]) + len(self.ps_wait)
        ndone = len(self.ps_done)
        self.ps_lock.release()
        return ndone == total
    
    def add(self, target, args):
        self.ps_lock.acquire()        
        target = self._decorate_return(target, self.process_key)
        p = mp.Process(target=target, args=args)
        p.key = self.process_key
        self.ps_wait.append(p)        
        self.process_key += 1
        self.ps_lock.release()


    def run(self, callback=None, show_progress=True):
        if self.run_thread is not None:
            assert not self.run_thread.isAlive(), "run thread should be dead, either not terminate all or a bug"
            del self.run_thread            
        p = threading.Thread(target=self._run, args=(callback,show_progress))
        self.run_thread = p
        p.start()
        #return self._run(callback=callback)
    
    def _run(self, callback=None, show_progress=True):
        # run all processes
        self.ps_lock.acquire()                
        self.ps_run = self.ps_wait[-self.max_size:][::-1]
        self.ps_wait = self.ps_wait[:-self.max_size]
        # assign gpu and start running
        for i, p in enumerate(self.ps_run):
            p.gpu = i % 7
        self._startAll()
        self.ps_lock.release()                
        
        # check if alive
        while True:
            try:
                # acquire lock for all the lists here
                self.ps_lock.acquire()        
                    
                done_list = [not p.is_alive() for p in self.ps_run]
                done_index = list(np.nonzero(done_list)[0])
                
                # put newly finished processes into ps_done
                for i in done_index:
                    p = self.ps_run[i]
                    p_repr = str(p)
                    if p_repr not in self.ps_done:
                        self.ps_done.add(p_repr)
                        if callback is not None:
                            callback(self.return_dict[p.key]) 
                    del p # prevent opening too many files error

                if show_progress:
                    print(self._progress()) # note only here is correct
                
                # add back new processes
                added_back = False
                while len(self.ps_wait) > 0 and len(done_index) > 0:
                    added_back = True
                    next_p = self.ps_wait.pop()
                    next_i = done_index.pop()
                    gpu_num = self.ps_run[next_i].gpu
                    next_p.gpu = gpu_num                    
                    self.ps_run[next_i] = next_p
                    next_p.start()
                    
                # finish the job
                if len(self.ps_wait) == 0 and np.all(done_list) and not added_back:
                    self.ps_run = []
                    self.ps_lock.release()                
                    break
                # release lock here
                self.ps_lock.release()                
                time.sleep(1)
            except:
                self.ps_lock.release()
                #self._terminateAll()
                raise
        
    def _startAll(self):
        for p in self.ps_run:
            p.start()

    def _terminateAll(self):
        self.ps_lock.acquire()    
        for p in self.ps_run:
            p.terminate()   
            self.ps_done.add(str(p))
            # p.join()
            del p
        for p in self.ps_wait:
            self.ps_done.add(str(p))
            del p
        self.ps_run = []
        self.ps_wait = []

        self.ps_lock.release()

        # make sure run_thread stops
        while (self.run_thread is not None) and self.run_thread.isAlive():
            print("waiting for run thread to finish")
            print("sleeping", self.ps_lock.locked(), self.progress())
            print(self.ps_run, self.ps_wait)
            time.sleep(1)
            
    def __repr__(self):        
        return self.progress()    
    

    def _progress(self):
        total = len(self.ps_done) + sum([p.is_alive() for p in self.ps_run]) + len(self.ps_wait)
        return "%d/%d done" % (len(self.ps_done), total)

    def progress(self):
        self.ps_lock.acquire()
        res = self._progress()
        self.ps_lock.release()                        
        return res

