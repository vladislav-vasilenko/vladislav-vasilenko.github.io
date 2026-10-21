/* Authenticated local catalog only. Neither credentials nor CVs enter employer DOM. */
async function loadCompanyCatalog(){
 let catalog;
 try{catalog=await LocalResumeService.request('/archive/company-settings',null,2500);await chrome.storage.local.set({company_catalog:catalog});}
 catch(error){catalog=(await chrome.storage.local.get('company_catalog')).company_catalog;if(!catalog)throw error;}
 globalThis.JobBoardAdapters?.configure(catalog.companies);return catalog;
}
