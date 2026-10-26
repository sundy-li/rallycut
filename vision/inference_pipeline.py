"""Bounded decode -> main-thread GPU -> ordered CPU postprocess pipeline.

Adapted from sundyli's local BlurBall MPS port (108e4f3 + working tree).
Unlike bare blocking Queue.put/get, failures/cancellation stop both workers and
propagate to the caller. No images/heatmaps accumulate for the whole video.
"""
import queue
import threading
import time


def run_batches(source, forward, consume, pipelined=True, queue_depth=2):
    if type(queue_depth) is not int or not 1<=queue_depth<=4:
        raise ValueError('queue depth must be 1-4')
    metrics={'producer_seconds':0.0,'forward_seconds':0.0,'postprocess_seconds':0.0,
             'batches':0,'input_queue_peak':0,'output_queue_peak':0}
    started=time.perf_counter()
    def next_item(iterator):
        start=time.perf_counter()
        try:
            return next(iterator)
        finally:
            metrics['producer_seconds']+=time.perf_counter()-start
    if not pipelined:
        iterator=iter(source)
        try:
            while True:
                try:batch=next_item(iterator)
                except StopIteration:break
                start=time.perf_counter();output=forward(batch)
                metrics['forward_seconds']+=time.perf_counter()-start
                start=time.perf_counter();consume(batch,output)
                metrics['postprocess_seconds']+=time.perf_counter()-start
                metrics['batches']+=1
        finally:
            if hasattr(iterator,'close'):iterator.close()
        metrics['wall_seconds']=time.perf_counter()-started
        return metrics

    inputs=queue.Queue(queue_depth)
    outputs=queue.Queue(queue_depth)
    errors=queue.Queue(1)
    stop=threading.Event()
    sentinel=object()
    def fail(error):
        try:errors.put_nowait(error)
        except queue.Full:pass
        stop.set()
    def check_error():
        try:error=errors.get_nowait()
        except queue.Empty:return
        raise error
    def put(channel,item):
        while not stop.is_set():
            try:
                channel.put(item,timeout=.05)
                return True
            except queue.Full:pass
        return False
    def take(channel):
        while not stop.is_set():
            try:return channel.get(timeout=.05)
            except queue.Empty:pass
        return sentinel
    def produce():
        iterator=None
        try:
            iterator=iter(source)
            while not stop.is_set():
                try:batch=next_item(iterator)
                except StopIteration:break
                if not put(inputs,batch):break
                metrics['input_queue_peak']=max(metrics['input_queue_peak'],inputs.qsize())
        except BaseException as error:
            fail(error)
        finally:
            try:
                if hasattr(iterator,'close'):iterator.close()
            except BaseException as error:
                fail(error)
            put(inputs,sentinel)
    def postprocess():
        try:
            while True:
                item=take(outputs)
                if item is sentinel:return
                batch,output=item
                start=time.perf_counter();consume(batch,output)
                metrics['postprocess_seconds']+=time.perf_counter()-start
        except BaseException as error:
            fail(error)
    producer=threading.Thread(target=produce,name='rallycut-decode',daemon=True)
    post=threading.Thread(target=postprocess,name='rallycut-postprocess',daemon=True)
    producer.start();post.start()
    try:
        while True:
            batch=take(inputs)
            check_error()
            if batch is sentinel:break
            start=time.perf_counter();output=forward(batch)
            metrics['forward_seconds']+=time.perf_counter()-start
            if not put(outputs,(batch,output)):
                check_error()
                raise InterruptedError('inference pipeline stopped')
            metrics['output_queue_peak']=max(metrics['output_queue_peak'],outputs.qsize())
            metrics['batches']+=1
        if not put(outputs,sentinel):check_error()
        # Timed joins keep signals/error checks responsive, unlike bare join().
        while producer.is_alive() or post.is_alive():
            producer.join(.05);post.join(.05);check_error()
        check_error()
    finally:
        stop.set()
        producer.join(2);post.join(2)
    metrics['wall_seconds']=time.perf_counter()-started
    return metrics
