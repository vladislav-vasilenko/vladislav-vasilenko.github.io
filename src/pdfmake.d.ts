declare module 'pdfmake/build/pdfmake' {
  const pdfMake: {
    addVirtualFileSystem(fonts:Record<string,string>):void;
    createPdf(definition:unknown):{download(filename:string):Promise<void>;getBlob():Promise<Blob>};
  };
  export default pdfMake;
}
declare module 'pdfmake/build/vfs_fonts' {
  const fonts:Record<string,string>;
  export default fonts;
}
