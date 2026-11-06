using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Text.Json;
using Mono.Cecil;
using Mono.Cecil.Cil;

class Program {
    static JsonSerializerOptions Options = new JsonSerializerOptions { WriteIndented=true, Encoder=System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping };
    static IEnumerable<TypeDefinition> AllTypes(IEnumerable<TypeDefinition> types) { foreach(var t in types) { yield return t; foreach(var n in AllTypes(t.NestedTypes)) yield return n; } }
    static void Save(string file, object data) { Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(file))); File.WriteAllText(file,JsonSerializer.Serialize(data,Options)); }
    static int Main(string[] args) {
        using var resolver=new DefaultAssemblyResolver();
        resolver.AddSearchDirectory(Path.GetDirectoryName(Path.GetFullPath(args[1])));
        var referenceDir=Environment.GetEnvironmentVariable("LM2_REFERENCE_DIR");
        if(!string.IsNullOrEmpty(referenceDir))resolver.AddSearchDirectory(referenceDir);
        using var a=AssemblyDefinition.ReadAssembly(args[1],new ReaderParameters { InMemory=true,ReadSymbols=false,AssemblyResolver=resolver });
        var types=AllTypes(a.MainModule.Types).ToList();
        if(args[0]=="dump") {
            var selected=types.Where(t=>t.FullName.Contains(args[3])).ToList();
            Save(args[2], selected.Select(t=>new { type=t.FullName,base_type=t.BaseType.FullName,fields=t.Fields.Select(f=>new {name=f.Name,type=f.FieldType.FullName}),methods=t.Methods.Select(m=>new { name=m.Name,parameters=m.Parameters.Select(p=>new {name=p.Name,type=p.ParameterType.FullName}),token=m.MetadataToken.ToString(),rva=m.RVA,instructions=m.HasBody?m.Body.Instructions.Select(i=>new{offset=i.Offset,op=i.OpCode.Name,operand=i.Operand?.ToString()}):null }) }));
            Console.WriteLine("Types: "+selected.Count); return 0;
        }
        if(args[0]=="calls") {
            Save(args[2],types.SelectMany(t=>t.Methods).Where(m=>m.HasBody).SelectMany(m=>m.Body.Instructions.Where(i=>i.Operand?.ToString().Contains(args[3])==true).Select(i=>new {type=m.DeclaringType.FullName,method=m.Name,offset=i.Offset,op=i.OpCode.Name,operand=i.Operand.ToString()}))); return 0;
        }
        if(args[0]=="noop") { a.Write(args[2]); Console.WriteLine("No-op written"); return 0; }
        if(args[0]=="probe" || args[0]=="quickprobe") {
            using var probe=AssemblyDefinition.ReadAssembly(args[3]);
            var boot=probe.MainModule.Types.Single(t=>t.Name=="LM2FontProbe").Methods.Single(m=>m.Name=="Boot");
            var awake=types.Single(t=>t.FullName=="L2Base.L2System").Methods.Single(m=>m.Name=="Awake");
            awake.Body.GetILProcessor().InsertBefore(awake.Body.Instructions[0],Instruction.Create(OpCodes.Call,a.MainModule.ImportReference(boot)));
            var steam=types.Single(t=>t.FullName=="SteamManager");
            foreach(var m in steam.Methods.Where(m=>m.Name=="Awake" || m.Name=="get_Initialized")) {
                m.Body.Instructions.Clear();m.Body.ExceptionHandlers.Clear();m.Body.Variables.Clear();
                if(m.Name=="get_Initialized")m.Body.Instructions.Add(Instruction.Create(OpCodes.Ldc_I4_0));
                else m.Body.Instructions.Add(Instruction.Create(OpCodes.Call,a.MainModule.ImportReference(boot)));
                m.Body.Instructions.Add(Instruction.Create(OpCodes.Ret));
            }
            if(args[0]=="quickprobe") {
                var update=types.Single(t=>t.FullName=="SystemModuleLoader").Methods.Single(m=>m.Name=="Update");
                var gate=update.Body.Instructions.Single(i=>i.Operand?.ToString()=="System.Boolean SteamManager::get_Initialized()");
                gate.OpCode=OpCodes.Ldc_I4_1;gate.Operand=null;
                var keys=types.Single(t=>t.FullName=="L2Base.L2System").Methods.Single(m=>m.Name=="getL2Keys");
                var press=probe.MainModule.Types.Single(t=>t.Name=="LM2FontProbe").Methods.Single(m=>m.Name=="Press");
                var il=keys.Body.GetILProcessor(); var first=keys.Body.Instructions[0];
                il.InsertBefore(first,Instruction.Create(OpCodes.Ldarg_1));il.InsertBefore(first,Instruction.Create(OpCodes.Ldarg_2));
                il.InsertBefore(first,Instruction.Create(OpCodes.Call,a.MainModule.ImportReference(press)));il.InsertBefore(first,Instruction.Create(OpCodes.Brfalse,first));
                il.InsertBefore(first,Instruction.Create(OpCodes.Ldc_I4_1));il.InsertBefore(first,Instruction.Create(OpCodes.Ret));
            }
            a.Write(args[2]);Console.WriteLine("Isolated font fixture; Steam disabled");return 0;
        }
        if(args[0]=="patch") {
            using var doc=JsonDocument.Parse(File.ReadAllText(args[3]));var edits=doc.RootElement.GetProperty("operations");
            var methods=types.SelectMany(t=>t.Methods).ToDictionary(m=>m.MetadataToken.ToUInt32());int count=0;
            var changed=new HashSet<string>();
            foreach(var op in edits.EnumerateArray()) {
                uint token=Convert.ToUInt32(op.GetProperty("method_token").GetString().Substring(2),16);int off=op.GetProperty("il_offset").GetInt32();
                var m=methods[token];var ins=m.Body.Instructions.Single(i=>i.Offset==off);
                if(ins.OpCode!=OpCodes.Ldstr || (string)ins.Operand!=op.GetProperty("before").GetString())throw new Exception("Source mismatch: "+m.FullName+" @ "+off);
                if(!changed.Add(token+":"+off))throw new Exception("Duplicate writer");
                ins.Operand=op.GetProperty("after").GetString();count++;
            }
            a.Write(args[2]);Console.WriteLine("Patched ldstr operands: "+count);return 0;
        }
        if(args[0]=="compare") {
            using var b=AssemblyDefinition.ReadAssembly(args[2]);
            var left=types.SelectMany(t=>t.Methods).ToDictionary(m=>m.FullName);
            var right=AllTypes(b.MainModule.Types).SelectMany(t=>t.Methods).ToDictionary(m=>m.FullName);
            if(left.Count!=right.Count || left.Keys.Except(right.Keys).Any())throw new Exception("Method inventory changed");
            var changes=new List<object>();int instr=0;
            foreach(var pair in left) {
                var x=pair.Value;var y=right[pair.Key];if(x.HasBody!=y.HasBody)throw new Exception("Body changed");if(!x.HasBody)continue;
                if(x.Body.Instructions.Count!=y.Body.Instructions.Count || x.Body.ExceptionHandlers.Count!=y.Body.ExceptionHandlers.Count || x.Body.Variables.Count!=y.Body.Variables.Count || x.Body.InitLocals!=y.Body.InitLocals)throw new Exception("Structure changed: "+pair.Key);
                for(int n=0;n<x.Body.Instructions.Count;n++) {
                    var i=x.Body.Instructions[n];var j=y.Body.Instructions[n];instr++;
                    if(i.OpCode!=j.OpCode)throw new Exception("Opcode changed: "+pair.Key);
                    if(i.Operand?.ToString()!=j.Operand?.ToString()) {
                        if(i.OpCode!=OpCodes.Ldstr)throw new Exception("Nonstring operand changed: "+pair.Key+" @ "+i.Offset);
                        changes.Add(new {method=pair.Key,offset=i.Offset,before=(string)i.Operand,after=(string)j.Operand});
                    }
                }
            }
            Save(args[3],new {methods=left.Count,instructions=instr,string_changes=changes.Count,changes});Console.WriteLine("String changes: "+changes.Count);return 0;
        }
        throw new Exception("Unknown command");
    }
}
