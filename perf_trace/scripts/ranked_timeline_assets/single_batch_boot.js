/* Historical single-batch schema adapter. All absolute ns arrive as strings. */
const D=JSON.parse(document.getElementById('page-payload').textContent);
const $=id=>document.getElementById(id),ns=v=>BigInt(v);
const PAYLOAD={origin_ns:D.scope.origin_ns,tables:{}};
const showDetails=value=>{$('detailText').textContent=JSON.stringify(value,null,2);};
