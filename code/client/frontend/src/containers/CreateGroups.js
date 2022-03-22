import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useCookies } from 'react-cookie';
import style from './styles';


export default function CreateGroups(props) {
  const { step, setStep, attributes, preferences, modules, 
          preferencesNumber, options, students } = props;
  const [groupsNumber, setGroupsNumber] = useState(null);
  const [minStudents, setMinStudents] = useState(null);
  const [maxStudents, setMaxStudents] = useState(null);
  const [sameDay, setSameDay] = useState(false);
  const [cookies, setCookie, removeCookie] = useCookies(
    ['groupsNumber', 'minStudents', 'maxStudents', 'preferencesBounds', 'email']
  );
  const [buttonText, setButtonText] = useState("Generar grupos")
  const [usedPreferences, setUsedPreferences] = useState(preferences.length)
  const [cookiesLoaded, setCookiesLoaded] = useState(false);
  const [email, setEmail] = useState("");
  const [isButtonDisabled, setIsButtonDisabled] = useState(false);
  const usedPreferencesOptions = [...Array(preferences.length + 1).keys()]

  let cap = {}
  let fDay = {}
  modules.forEach(module => {
    cap[module] = students.length;
    fDay[module] = {};
    preferences.forEach(pref => {
      fDay[module][pref] = false;
    })
  })
  const [fixedDay, setFixedDay] = useState(fDay);
  const [capacity, setCapacity] = useState(cap);

  let bnd = {}
  Object.keys(options).map((attribute, index) => {
    Object.keys(options[attribute]).map((key, index) => {
      bnd[key] = {"min": 0, "max": maxStudents, "solo": false}
    })
  })
  const [bounds, setBounds] = useState(bnd);

  let pBnd = {}
  preferences.forEach(pref => {
    pBnd[pref] = {"min": 0, "max": groupsNumber}
  })
  const [prefsBounds, setPrefsBounds] = useState(pBnd);


  useEffect(displayCookies, []);


  function validate() {
    if (students.length/groupsNumber <= maxStudents && students.length/groupsNumber >= minStudents) {
      return true
    } else {
      alert("Alguno de los parametros ingresados en Ajustes generales provoca infactibilidad en el modelo. Por favor revisar y volver a intentar.")
      return false
    }
  }
  
  async function runModelRequest() {
    if (validate()) {
      setCookie('groupsNumber', parseInt(groupsNumber), { path: '/' })
      setCookie('minStudents', parseInt(minStudents), { path: '/' })
      setCookie('maxStudents', parseInt(maxStudents), { path: '/' })
      setCookie('email', email, { path: '/' })
      setCookie('preferencesBounds', prefsBounds, { path: '/' })
      const body = {attributes, 
                    preferences, 
                    groupsNumber, 
                    minStudents, 
                    maxStudents,
                    bounds,
                    students,
                    capacity,
                    preferencesNumber,
                    options,
                    prefsBounds,
                    usedPreferences,
                    modules,
                    email,
                    tmax: 60,
                    sameDay,
                    fixedDay }
        console.log(body)
        try {
          setIsButtonDisabled(true);
          setButtonText("Enviando datos")
          await axios.post('/dev/run_model/', body);
          setIsButtonDisabled(false);
          alert("Tus datos han sido enviados existosamente al servidor. Te enviaremos los resultados por email cuando estén listos. El tiempo máximo de espera es de una hora")
          setButtonText("Generar grupos nuevamente")
        } catch (error) {
          console.error(error);
          alert("Ha ocurrido un error. Por favor inténtelo de nuevo")
          setIsButtonDisabled(false);
        }
    }
  }

  function displayCookies() {
    if (cookies && !cookiesLoaded) {
      if (cookies.groupsNumber) {
        setGroupsNumber(parseInt(cookies.groupsNumber))
      }
      if (cookies.minStudents) {
        setMinStudents(parseInt(cookies.minStudents))
      }
      if (cookies.maxStudents) {
        setMaxStudents(parseInt(cookies.maxStudents))
      }
      if (cookies.email) {
        setEmail(email)
      }
      setCookiesLoaded(true);
    }
  }

  function createSettings() {
    const optionsToShow = [<tr><td>
      Cantidad de grupos ({students.length} alumnos):
      <input style={{float:"right", width: "60px"}} size="4" type="number" 
              name="groupsNumber" defaultValue={parseInt(groupsNumber)} onChange={(e) => setGroupsNumber(parseInt(e.target.value))}/>
      </td></tr>,
      <tr><td>
      Minimo de estudiantes por grupo:
      <input style={{float:"right", width: "60px"}} size="4" type="number" 
              name="minStudents" defaultValue={parseInt(minStudents)}  onChange={(e) => setMinStudents(parseInt(e.target.value))}/>
      </td></tr>,
      <tr><td>
      Maximo de estudiantes por grupo:
      <input style={{float:"right", width: "60px"}}  size="4" type="number" 
              name="maxStudents" defaultValue={parseInt(maxStudents)}  onChange={(e) => setMaxStudents(parseInt(e.target.value))}/>
      </td></tr>,
      <tr><td>
      Email al cual se enviarán los resultados:
      <input style={{float:"right", width: "200px"}}  size="10" type="text" 
              name="email" defaultValue={email}  onChange={(e) => setEmail(e.target.value)}/>
      </td></tr>,
      ]
    return optionsToShow
  };

  return (
    <div>
      <div style={style.cont}>
        <h3> Ajustes generales </h3>
        <table>
          <tbody>
          {createSettings()}
          </tbody>
        </table>
      </div>

      {attributes.length !== 0 && (
            <div style={style.cont}>
              <h3> Atributos </h3>
                {Object.keys(options).map((key, index) => {
                  return <Attribute name={key} 
                                    options={options[key]} 
                                    attributes={options} 
                                    setBounds={setBounds}
                                    bounds={bounds}
                                    groupsNumber={groupsNumber}
                                    maxStudents={maxStudents}/>
                })}
            </div>
      )}

      {modules.length !== 0 && 
      <div style={style.cont}>
        <h3> Secciones </h3>
      <p></p> 
      <div>
        <p style={{display: "inline-block", paddingRight: 10}}> Grupos con el mismo tema deben ser asignados en la misma seccion: </p>
        <button style={{display: "inline-block"}} onClick={() => setSameDay(!sameDay)}> {sameDay ? "Desactivar" : "Activar"} </button>
      </div>
      <p></p> 
        {modules.map((mod, index) => {
            return  <Module key={index}
                            module={mod} 
                            preferences={preferences} 
                            fixedDay={fixedDay} 
                            setFixedDay={setFixedDay}
                            capacity={capacity}
                            setCapacity={setCapacity}
                            students={students}/>
          })}
      </div>
      }
      
      {preferences.length !== 0 && (
            <div style={style.cont}>
              <h3> Temas </h3>
              <p></p>
              <label>Cantidad de temas a utilizar: </label>
              <select value={usedPreferences} onChange={(e) => setUsedPreferences(parseInt(e.target.value))}>
              {usedPreferencesOptions.map((x,y) => (<option key={y}>{x}</option>))}
              </select>
              <p></p> 
              {preferences.map((pref, index) => {
              return <Preference key={index}
                                  pref={String(pref)} 
                                  setPrefsBounds={setPrefsBounds}
                                  prefsBounds={prefsBounds} 
                                  groupsNumber={groupsNumber} />
              })}
          </div>
      )}

      <div style={{paddingLeft: 25}}>
        <button onClick={() => setStep(step - 1)}>
          Atras
        </button>
        <button disabled={isButtonDisabled} onClick={runModelRequest}>
          {buttonText}
        </button>
      </div>
      
    </div>
    );
};

function Attribute(props) {
  const { name, options, attributes, setBounds, bounds, maxStudents } = props;
  const [check, setCheck] = useState({})
  const [showSettings, setShowSettings] = useState(false);

  useEffect(() => {
    let c = check;
    for (const [key, value] of Object.entries(options)) {
      c[key] = "Activar";
    }
    setCheck(c);
  }, []);

  function editOption(value, key, type) {
    let b = bounds;
    b[key][type] = parseInt(value.target.value);
    setBounds(b);
  }

  function changeRadio(key) {
    let b = bounds;
    let c = check;
    b[key]["solo"] = !b[key]["solo"]
    if (!b[key]["solo"]) {
      c[key] = "Activar";
    } else {
      c[key] = "Desactivar";
    }
    setCheck({...c, key: "Desactivar"});
    setBounds(b);
  }

  function createOptions() {
    let optionsToShow = []
    for (const [key, value] of Object.entries(options)) {
        optionsToShow.push(<tr> 
                            <td><h5>{key}</h5><p>({attributes[name][key]} alumnos marcaron esta opcion)</p></td>
                          </tr>)
        optionsToShow.push(<tr> 
                            <td>Min: <input defaultValue={bounds[key]["min"]} style={{width: "60px"}} type="number" name="min" onChange={(value) => editOption(value, key, "min")}/> </td>
                            <td>Max: <input defaultValue={bounds[key]["max"] === null? maxStudents : bounds[key]["max"]} style={{width: "60px"}} type="number" name="max" onChange={(value) => editOption(value, key, "max")}/> </td>
                           </tr>)
        optionsToShow.push(<tr> 
                            <td> Pueden haber grupos sin esta característica: <button onClick={() => changeRadio(key)}> {check[key]} </button> </td>
                          </tr>)
        optionsToShow.push(<tr> 
                             <td><p></p></td>
                          </tr>)
    }
    return optionsToShow
  };

  return (
      <div>
        <div>
          <h4 style={{display: "inline-block", paddingRight: 10}} >- {name} </h4>
          <button style={{display: "inline-block"}} onClick={() => setShowSettings(!showSettings)}>Ajustes</button>
        </div>
        { showSettings &&
          <div key={maxStudents}>
          <table>
          <tbody>
          {createOptions()}
          </tbody>
          </table>
          </div>
        }
      </div>
    );
}

function Preference(props) {
  const { key, pref, prefsBounds, setPrefsBounds, groupsNumber} = props;
  const [showPreference, setShowPreference] = useState(false);


  function editPreference(e, pref, type) {
    let prefs = prefsBounds;
    prefs[pref][type] = parseInt(e.target.value);
    setPrefsBounds(prefs);
  }

  return (
    <div> 
      <div>
        <h4 style={{display: "inline-block", paddingRight: 10}} >- {pref} </h4>
        <button style={{display: "inline-block"}} onClick={() => setShowPreference(!showPreference)}>Ajustes</button>
      </div>
      {showPreference && 
        <div key={key}>
          <table>
          <tbody>
          <tr>
            <td> 
              Mín. cantidad de grupos armados con este tema: <input defaultValue={prefsBounds[pref]["min"]} style={{float:"right", width: "60px"}}  maxLength="4" type="number" name={pref} onChange={(e) => editPreference(e, pref, "min")}/> 
            </td>
          </tr>
          <tr>
            <td>
              Máx. cantidad de grupos armados con este tema: 
              <input defaultValue={prefsBounds[pref]["max"] === null? groupsNumber : prefsBounds[pref]["max"]} style={{float:"right", width: "60px"}}  maxLength="4" type="number" name={pref} onChange={(e) => editPreference(e, pref, "max")}/>
            </td>
          </tr>
          </tbody>
          </table>
        </div>
      }
    </div>
  )
}

function Module(props) {
  const {key, module, preferences, fixedDay, setFixedDay, capacity, setCapacity, students} = props;
  const [show, setShow] = useState(false);

  function editFixedDay(pref, value) {
    let f = fixedDay[module];
    f[pref] = value;
    setFixedDay({...fixedDay, module: f});
  }

  function editModule(e) {
    let cap = capacity;
    cap[module]= parseInt(e.target.value);
    setCapacity(cap);
  }

  return (
    <div>
      <div>
        <h4 style={{display: "inline-block", paddingRight: 10}} >- {module} </h4>
        <button style={{display: "inline-block"}} onClick={() => setShow(!show)}>Ajustes</button>
      </div>
    {show && (
      <div key={key}>
          <label> Capacidad: </label>
          <input style={{width: "60px"}} defaultValue={capacity[module]} size="4" type="number" name={module} onChange={(e) => editModule(e)}/> 
          <label> alumnos </label>
          <p></p>
          <table>
            <tbody>
            {preferences.map((pref, index) => {
            return <tr> <td>Tema {pref} solo puede estar presente en esta seccion: <button onClick={() => editFixedDay(pref, !fixedDay[module][pref])}> {fixedDay[module][pref] ? "Desactivar" : "Activar"} </button></td></tr>
          })}
            </tbody>
          </table>
      </div>
    )}
    </div>
  )
}
