WebGPU exposes the device GPU to the browser and runs matrix multiplication orders of magnitude faster
than the CPU path for transformer inference. When a browser does not expose navigator.gpu, the runtime
degrades to WASM, which is slower but available everywhere.
