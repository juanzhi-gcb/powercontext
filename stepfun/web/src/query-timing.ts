/** Enclose every user-visible query stage, including an asynchronous renderer. */
export async function measureQuery<T>(
  embed: (() => Promise<number[]>) | null,
  retrieve: (vector: number[] | null) => Promise<T>,
  render: (response: T) => void | Promise<void>,
): Promise<{ response: T; queryEmbedMs: number; endToEndMs: number }> {
  const started = performance.now();
  const vector = embed ? await embed() : null;
  const queryEmbedMs = embed ? performance.now() - started : 0;
  const response = await retrieve(vector);
  await render(response);
  return { response, queryEmbedMs, endToEndMs: performance.now() - started };
}
