// Development aid: compare named C2 functions to the minified upstream export.
// This never rewrites or executes either runtime.
import fs from 'node:fs';
import {parse} from '@babel/parser';

function inspect(file) {
    const source = fs.readFileSync(file, 'utf8');
    const tree = parse(source, {sourceType:'script'});
    const functions=[];
    function walk(node, parent) {
        if (!node || typeof node !== 'object') return;
        if (['FunctionExpression','FunctionDeclaration'].includes(node.type)) {
            const literals=[];
            function scan(n) {
                if (!n || typeof n !== 'object') return;
                if (n.type==='StringLiteral' && n.value.length>2) literals.push(n.value);
                for (const [k,v] of Object.entries(n)) {
                    if (['loc','start','end','extra'].includes(k)) continue;
                    if (Array.isArray(v)) v.forEach(scan); else if (v && typeof v==='object') scan(v);
                }
            }
            scan(node.body);
            functions.push({name:node.id?.name || (parent?.type==='AssignmentExpression' ? source.slice(parent.left.start,parent.left.end):'?'),
                literals:new Set(literals), text:source.slice(node.start,node.end)});
        }
        for (const [k,v] of Object.entries(node)) {
            if (['loc','start','end','extra'].includes(k)) continue;
            if (Array.isArray(v)) v.forEach(n=>walk(n,node)); else if (v && typeof v==='object') walk(v,node);
        }
    }
    walk(tree);
    return functions;
}
const named=inspect('c2-sans-fight-derivative-backup/c2runtime.js');
const minified=inspect('c2-sans-fight/c2runtime.js');
if (process.argv[2]==='--min') {
    for (const f of minified.filter(f=>process.argv.slice(3).includes(f.name))) console.log(f.name+' = '+f.text);
    process.exit(0);
}
for (const name of process.argv.slice(2)) {
    for (const old of named.filter(f=>f.name===name)) {
        const matches=minified.map(f=>({f,score:[...old.literals].filter(x=>f.literals.has(x)).length / Math.max(1,new Set([...old.literals,...f.literals]).size)})).sort((a,b)=>b.score-a.score).slice(0,2);
        console.log(JSON.stringify({name,literals:[...old.literals],matches:matches.map(({f,score})=>({name:f.name,score,text:f.text}))}));
    }
}
