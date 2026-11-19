/** Invalidate late responses as well as aborting the underlying request. */
export class RequestScope {
  private controller: AbortController | null = null;

  begin() {
    this.invalidate();
    const controller = new AbortController();
    this.controller = controller;
    return {
      signal: controller.signal,
      isCurrent: () => this.controller === controller && !controller.signal.aborted,
    };
  }

  invalidate() {
    this.controller?.abort();
    this.controller = null;
  }
}
