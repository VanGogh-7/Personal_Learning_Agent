# Concurrency and Scalability Review

Use this reference when reviewing asynchronous execution, concurrent requests, worker configuration, queues, databases, external APIs, or expected growth.

## 1. Start from the workload

Before proposing a solution, identify:

* request type;
* expected concurrent users;
* average and tail latency;
* CPU-bound versus I/O-bound work;
* request duration;
* external provider latency;
* provider rate limits;
* database query volume;
* memory consumption per request;
* whether work must finish before returning a response;
* whether work may be retried safely.

Do not infer system capacity from user count alone.

A hundred users sending one request per hour is different from a hundred simultaneous long-running requests.

## 2. Identify the bottleneck

Possible bottlenecks include:

* CPU;
* memory;
* database connections;
* database locks;
* network sockets;
* external LLM quotas;
* embedding-provider quotas;
* file descriptors;
* thread pools;
* process workers;
* queue depth;
* storage bandwidth;
* token cost.

Scaling the web server does not fix a bottleneck in an external provider or database.

## 3. Async I/O

Async I/O is appropriate when a request spends substantial time waiting for:

* LLM APIs;
* databases with asynchronous drivers;
* HTTP services;
* object storage;
* network file operations.

Async I/O does not make CPU-heavy work faster.

CPU-heavy parsing, OCR, embedding on local hardware, or numerical processing may require:

* a process pool;
* a separate worker;
* a native extension;
* a dedicated service.

Check for blocking functions called inside async request handlers.

## 4. Bounded concurrency

Never create unbounded tasks based directly on user input.

Use:

* semaphores;
* bounded worker pools;
* bounded queues;
* provider-specific concurrency limits;
* per-user limits;
* cancellation;
* request deadlines.

Unbounded concurrency can exhaust memory, connections, file descriptors, or provider quotas.

## 5. Backpressure

Backpressure means slowing or rejecting incoming work when downstream components cannot keep up.

Possible mechanisms:

* bounded queues;
* HTTP 429 responses;
* admission control;
* per-tenant quotas;
* concurrency limits;
* load shedding;
* delayed processing.

A queue delays overload; it does not remove overload.

Track queue length and queue wait time.

## 6. Web request versus background job

Keep work in the request path when:

* it is short;
* the user needs the result immediately;
* cancellation should stop the work;
* failure can be returned directly.

Move work to a background job when:

* it is long-running;
* it should survive client disconnection;
* it needs retries;
* it processes large files;
* it can complete asynchronously;
* it needs controlled worker concurrency.

Typical Agent examples:

* chat response: usually request path or streaming request;
* PDF ingestion: usually background job;
* OCR: background job;
* reindexing: background job;
* evaluation suite: background job;
* periodic cleanup: scheduled job.

## 7. Database connections

A database connection pool is finite.

Check:

* pool size;
* maximum overflow;
* number of application processes;
* total possible connections;
* transaction duration;
* idle transactions;
* slow queries;
* indexes;
* connection release on errors.

Total possible application connections may be approximately:

`instances × processes per instance × pool size`

Do not independently maximize every layer.

## 8. Shared state

In-process memory is not shared reliably across:

* multiple processes;
* multiple containers;
* multiple machines;
* application restarts.

Do not store critical shared state only in:

* Python dictionaries;
* module-level variables;
* process-local caches.

Use persistent or shared storage when the state must survive restart or coordinate instances.

## 9. Duplicate execution and idempotency

Retries, client reconnections, queue redelivery, and network uncertainty can cause duplicate execution.

For side-effecting operations, define:

* idempotency key;
* uniqueness constraint;
* operation status;
* retry behavior;
* recovery behavior.

Examples include:

* charging money;
* inserting the same document twice;
* sending email;
* executing a tool;
* writing long-term memory;
* creating an external resource.

## 10. Scaling sequence

Prefer this sequence unless evidence justifies another path:

1. Measure.
2. Fix obvious blocking and slow operations.
3. Add timeouts and bounded concurrency.
4. Tune database queries and connection pools.
5. Separate long-running jobs.
6. Add caching only for measured repeated work.
7. Scale application instances horizontally.
8. Introduce distributed coordination only when multiple instances require it.
9. Adopt more complex infrastructure only after identifying the limiting component.

## 11. Review output

For each scalability concern, report:

* workload assumption;
* current bottleneck;
* failure mode;
* evidence;
* immediate mitigation;
* long-term option;
* adoption threshold;
* measurement required.

Avoid vague statements such as “this will not scale.”

