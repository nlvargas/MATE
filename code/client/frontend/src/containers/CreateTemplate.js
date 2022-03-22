import React, { useState, useEffect } from 'react';
import XLSX from 'xlsx';
import { saveAs } from 'file-saver';
import { useCookies } from 'react-cookie';
import style from './styles';


export default function CreateTemplate(props) {
  const { step, setStep, attributes, setAttributes,
          preferences, setPreferences, modules, setModules,
          preferencesNumber, setPreferencesNumber } = props;
  const [cookies, setCookie, removeCookie] = useCookies(
    ['attributes', 'preferences', 'modules', 'preferencesNumber']
  );
  const [haveAttributes, setHaveAttributes] = useState(false);
  const [havePreferences, setHavePreferences] = useState(false);
  const [haveModules, setHaveModules] = useState(false);
  const [newAttribute, setNewAttribute] = useState("");
  const [newPreference, setNewPreference] = useState("");
  const [newModule, setNewModule] = useState("");
  const [showLink, setShowLink] = useState(false);
  const [wbout, setWbout] = useState("");
  const [cookiesLoaded, setCookiesLoaded] = useState(false);
  const [preferencesNumberOptions, setPreferencesNumberOptions] = useState([...Array(preferencesNumber + 1).keys()])


  useEffect(() => {
    if (cookies && !cookiesLoaded) {
      console.log(cookies)
      if (cookies.attributes) {
        setAttributes(cookies.attributes)
        setHaveAttributes(true)
      }
      if (cookies.preferences) {
        setPreferences(cookies.preferences)
        setPreferencesNumberOptions([...Array(cookies.preferences.length + 1).keys()])
        setHavePreferences(true)
      }
      if (cookies.preferencesNumber) {
        setPreferencesNumber(cookies.preferencesNumber)
        setHavePreferences(true)
      }
      if (cookies.modules) {
        setModules(cookies.modules)
        setHaveModules(true)
      }
      setCookiesLoaded(true);
    }
  })

  function addAttribute() {
    setAttributes(attributes.concat(newAttribute));
    setNewAttribute("");
  }

  function keyAddAttribute(event) {
    if (event.key === "Enter") {
      addAttribute();
    }
  }

  function addPreference() {
    setPreferences(preferences.concat(newPreference));
    setNewPreference("");
    setPreferencesNumberOptions(preferencesNumberOptions.concat(preferencesNumberOptions.length));
  }

  function keyAddPreference(event) {
    if (event.key === "Enter") {
      addPreference();
    }
  }

  function addModule() {
    setModules(modules.concat(newModule));
    setNewModule("");
  }

  function keyAddModule(event) {
    if (event.key === "Enter") {
      addModule();
    }
  }

  function removePreference(index) {
    let i = 0;
    let p = [];
    preferences.forEach(pref => {
      if (i !== index) {
        p.push(pref)
      }
      i++
    })
    setPreferences(p);
    setPreferencesNumberOptions(preferencesNumberOptions.slice(0, -1));
  }

  function removeModule(index) {
    let i = 0;
    let m = [];
    modules.forEach(mod => {
      if (i !== index) {
        m.push(mod)
      }
      i++
    })
    setModules(m);
  }

  function removeAttribute(index) {
    let i = 0;
    let a = [];
    attributes.forEach(attr => {
      if (i !== index) {
        a.push(attr)
      }
      i++
    })
    setAttributes(a);
  }

  function generateTemplate() {
    let wb = XLSX.utils.book_new();
    wb.SheetNames.push("Alumnos");
    let r = ["Nombre"]
    attributes.forEach(attr => {
      r.push(attr);
    })
    modules.forEach(mod => {
      r.push("Disponibilidad " + mod)
    })
    let prefNumber = 1
    while (prefNumber <= preferencesNumber) {
      r.push("Preferencia " + prefNumber.toString())
      prefNumber++;
    }
    let ws_data = []
    ws_data.push(r)
    let ws = XLSX.utils.aoa_to_sheet(ws_data);
    wb.Sheets["Alumnos"] = ws;
    setWbout(XLSX.write(wb, {bookType:'xlsx', type: 'binary'}));
    setShowLink(true)
  }

  function downloadTemplate() {

    function s2ab(s) { 
      var buf = new ArrayBuffer(s.length); 
      var view = new Uint8Array(buf); 
      for (var i=0; i<s.length; i++) view[i] = s.charCodeAt(i) & 0xFF; 
      return buf;    
    }

    saveAs(new Blob([s2ab(wbout)], {type:"application/octet-stream"}), 'template.xlsx');
  }

  function next() {
    setCookie('attributes', attributes, { path: '/' })
    setCookie('modules', modules, { path: '/' })
    setCookie('preferences', preferences, { path: '/' })
    setCookie('preferencesNumber', preferencesNumber, { path: '/' })
    setStep(step + 1)
  }

  return (
    
    <div style={{justifyContent:'center', alignItems:'center'}}>

      <div style={style.cont}>
        <h3> Atributos </h3>

        <p style={{fontSize: '14px', paddingVertical: 20, textAlign: 'justify'}}>
          Los atributos son características generales que puede tener cada alumno (Ej: Género, Universidad, Región, Edad, entre otros). Con estas características luego se podrán imponer restricciones duras sobre los integrantes de cada grupo (Ej: que no queden alumnos de la misma universidad juntos, que no queden mujeres solas en un grupo, etc.)
        </p>
        <div>
          <p style={{fontSize: '14px', display: "inline-block", paddingRight: 10}}>
            ¿Tienen atributos los alumnos de los grupos que quieres armar?
          </p>
          <button style={{display: "inline-block"}} onClick={() => setHaveAttributes(!haveAttributes)}>
            {!haveAttributes? "Sí" : "No"}
          </button>
        </div>

        {haveAttributes && (
          <div>
            <table>
              <tbody>
              {attributes.map((item, index) => (
                <tr key={index}>
                  <td style={{paddingRight: "20px"}}><p style={{display: "inline-block"}}> {item} </p></td>
                  <td style={{paddingRight: "20px"}}><button style={{display: "inline-block"}} onClick={() => removeAttribute(index)}>Eliminar</button></td>
                </tr>
              ))}
              </tbody>
            </table>
            <input type="text" value={newAttribute} onKeyPress={e => keyAddAttribute(e)} onChange={e => setNewAttribute(e.target.value)}/>
            <button onClick={addAttribute}> Agregar atributo </button>
          </div>
        )}
      </div>


      <div style={style.cont}>
        <h3> Secciones </h3>

        <p style={{fontSize: '14px', paddingVertical: 20, textAlign: 'justify'}}>
          Las secciones se utilizan cuando es necesario validar la disponibilidad de un alumno para pertenecer a un determinado grupo. Por ejemplo, podrían haber 4 opciones de horarios/secciones para asistir a cierto curso en las que cada alumno debe marcar su disponibilidad para conformar un grupo cada horario/sección. Luego, el programa utiliza esta información para conformar grupos solo en los cuales todos sus integrantes tengan disponibilidad para trabajar en ese horario/sección. 
        </p>

        <div>
          <p style={{fontSize: '14px', display: "inline-block", paddingRight: 10}}>
            ¿Es necesario considerar secciones en los grupos a conformar?
          </p>
          <button style={{display: "inline-block"}} onClick={() => setHaveModules(!haveModules)}>
            {!haveModules? "Sí" : "No"}
          </button>
        </div>

        {haveModules && (
          <div>
            <table>
              <tbody>
              {modules.map((item, index) => (
                <tr key={index}>
                  <td style={{paddingRight: "20px"}}><p style={{display: "inline-block"}}> {item} </p></td>
                  <td style={{paddingRight: "20px"}}><button style={{display: "inline-block"}} onClick={() => removeModule(index)}>Eliminar</button></td>
                </tr>
              ))}
              </tbody>
            </table>
            <input type="text" value={newModule} onKeyPress={e => keyAddModule(e)} onChange={(e) => setNewModule(e.target.value)}/>
            <button onClick={addModule}> Agregar sección </button>  
          </div>
        )}
      </div>


      <div style={style.cont}>
        <h3> Temas </h3>

        <p style={{fontSize: '14px', paddingVertical: 20, textAlign: 'justify'}}>
        Los temas corresponden a tópicos que se asignan a un determinado grupo según la preferencia que le dieron a ese tópico los integrantes del grupo. Por ejemplo, pueden haber 3 temas posibles a discutir en cada grupo y cada alumno los ordena según sus gustos. Luego el programa al conformar los grupos intentará que cada alumno quede asignado a un grupo con un tema de su gusto
        </p>

        <div>
          <p style={{fontSize: '14px', display: "inline-block", paddingRight: 10}}>
            ¿Es necesario que los grupos formados esten asociados a algún tema?
          </p>
          <button style={{display: "inline-block"}} onClick={() => setHavePreferences(!havePreferences)}>
            {!havePreferences? "Sí" : "No"}
          </button>
        </div>

        {havePreferences && (
          <div>
            <table>
              <tbody>
              {preferences.map((item, index) => (
                <tr key={index}>
                  <td style={{paddingRight: "20px"}}><p style={{display: "inline-block"}}> {item} </p></td>
                  <td style={{paddingRight: "20px"}}><button style={{display: "inline-block"}} onClick={() => removePreference(index)}>Eliminar</button></td>
                </tr>
              ))}
              </tbody>
            </table>
            <input type="text" value={newPreference} onKeyPress={e => keyAddPreference(e)} onChange={(e) => setNewPreference(e.target.value)}/>
            <button onClick={addPreference}> Agregar tema </button>

            <p></p>

            <label>Cantidad de temas que cada alumno debe ordenar segun sus preferencias</label>
            <select value={preferencesNumber} onChange={(e) => setPreferencesNumber(parseInt(e.target.value))}>
              {preferencesNumberOptions.map((x,y) => (<option key={y}>{x}</option>))}
            </select>
          </div>
        )}
      </div>


      <div style={style.cont}>
        <button onClick={generateTemplate}> Crear Template </button>
        {showLink && 
          <button onClick={downloadTemplate}> Descargar template </button>
        }
      </div>
      
      <div style={{paddingLeft: 25}}>
        <button onClick={next}> Siguiente </button>
      </div>
  

    </div>
    );
};
