// react_frontend_modern/src/global.d.ts
interface Window {
  vis: {
    Network: new (container: HTMLElement, data: any, options: any) => any;
    DataSet: new (data?: any[]) => any;
  };
  CONFIG: { BACKEND_API_URL: string };
}
